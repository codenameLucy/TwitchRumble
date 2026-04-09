"""
test_fight.py — Local fight test, no Twitch connection required.

Spins up just the WebSocket server and runs a full automated fight
so you can verify the overlay looks and behaves correctly in OBS.

Usage:
    python3 test_fight.py

Optional arguments:
    --fighters  "Name1" "Name2"   Custom fighter names  (default: TestFighter1 TestFighter2)
    --timer     <seconds>         Move selection window (default: 5)
    --delay     <seconds>         Pause between rounds  (default: 3)
    --port      <port>            WebSocket port        (default: 8765, matches overlay.js)
    --avatar1   <url>             Avatar URL for fighter 1
    --avatar2   <url>             Avatar URL for fighter 2

Example:
    python3 test_fight.py --fighters "StreamerA" "StreamerB" --timer 3
"""

import asyncio
import json
import random
import argparse
import websockets

from rumble.main import Fighter, calc_damage

# ── WebSocket broadcast ────────────────────────────────────────────────────────

connected_clients: set = set()

async def ws_handler(websocket):
    connected_clients.add(websocket)
    print(f"[WS] Overlay connected ({len(connected_clients)} client(s))")
    try:
        await websocket.wait_closed()
    finally:
        connected_clients.discard(websocket)
        print(f"[WS] Overlay disconnected ({len(connected_clients)} client(s))")

async def broadcast(msg: dict):
    if not connected_clients:
        return
    data = json.dumps(msg)
    await asyncio.gather(
        *[c.send(data) for c in connected_clients],
        return_exceptions=True
    )

# ── Test scenario ──────────────────────────────────────────────────────────────

async def run_test(
    name1: str,
    name2: str,
    avatar1: str,
    avatar2: str,
    move_timer: int,
    round_delay: int,
):
    print(f"\n{'─'*50}")
    print(f"  TEST FIGHT: {name1}  vs  {name2}")
    print(f"  Move timer: {move_timer}s | Round delay: {round_delay}s")
    print(f"{'─'*50}\n")

    # Wait a moment for the overlay to connect before starting
    print("[Test] Waiting 2s for overlay to connect — open overlay.html in OBS now...")
    await asyncio.sleep(2)

    f1 = Fighter(name1)
    f2 = Fighter(name2)

    print(f"[Test] {f1.name}: {f1.type} type | {f1.hp} HP")
    print(f"[Test] {f2.name}: {f2.type} type | {f2.hp} HP\n")

    # ── Queue animation ──
    await broadcast({"event": "queue_update", "queue": [f1.name]})
    await asyncio.sleep(1)
    await broadcast({"event": "queue_update", "queue": [f1.name, f2.name]})
    await asyncio.sleep(1)

    # ── Fight start ──
    await broadcast({
        "event":    "fight_start",
        "fighter1": {**f1.to_dict(), "avatar": avatar1},
        "fighter2": {**f2.to_dict(), "avatar": avatar2},
    })
    print("[Test] Fight started — VS splash showing\n")
    await asyncio.sleep(3)

    # ── Rounds ──
    round_num = 0
    while f1.hp > 0 and f2.hp > 0:
        round_num += 1
        f1.choice = None
        f2.choice = None

        await broadcast({
            "event":    "round_start",
            "round":    round_num,
            "timer":    move_timer,
            "fighter1": f1.to_dict(),
            "fighter2": f2.to_dict(),
        })
        print(f"[Test] Round {round_num} — timer: {move_timer}s")

        # Simulate move selection: each fighter picks randomly after a short delay.
        # The delay is randomised so they don't always select at exactly the same time,
        # mirroring the real flow where chatters type at different moments.
        async def pick_move(fighter: Fighter, label: str):
            await asyncio.sleep(random.uniform(1, move_timer - 1))
            fighter.choice = random.randint(0, 3)
            move_name = fighter.moves[fighter.choice][0]
            print(f"[Test]   {label} chose move {fighter.choice + 1}: {move_name}")

        await asyncio.gather(
            pick_move(f1, f1.name),
            pick_move(f2, f2.name),
        )

        dmg1, multi1 = calc_damage(f1, f1.choice, f2)
        dmg2, multi2 = calc_damage(f2, f2.choice, f1)

        f2.hp = max(0, f2.hp - dmg1)
        f1.hp = max(0, f1.hp - dmg2)

        print(f"[Test]   {f1.name} dealt {dmg1} dmg (×{multi1}) → {f2.name} now {f2.hp} HP")
        print(f"[Test]   {f2.name} dealt {dmg2} dmg (×{multi2}) → {f1.name} now {f1.hp} HP\n")

        await broadcast({
            "event":    "round_result",
            "round":    round_num,
            "fighter1": {**f1.to_dict(), "move_used": f1.choice, "damage_dealt": dmg1, "effectiveness": multi1},
            "fighter2": {**f2.to_dict(), "move_used": f2.choice, "damage_dealt": dmg2, "effectiveness": multi2},
        })

        await asyncio.sleep(round_delay)

    # ── Fight end ──
    if f1.hp <= 0 and f2.hp <= 0:
        winner = None
        print("[Test] Result: DRAW")
    elif f1.hp <= 0:
        winner = f2.name
        print(f"[Test] Result: {f2.name} wins!")
    else:
        winner = f1.name
        print(f"[Test] Result: {f1.name} wins!")

    await broadcast({
        "event":    "fight_end",
        "winner":   winner,
        "fighter1": f1.to_dict(),
        "fighter2": f2.to_dict(),
    })

    print("\n[Test] Fight complete. Overlay will return to idle in 8s.")
    print("[Test] Press Ctrl+C to stop the server.\n")

# ── Entry point ────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local test fight for the Twitch Boxing Ring overlay."
    )
    parser.add_argument("--fighters", nargs=2, metavar=("NAME1", "NAME2"),
                        default=["TestFighter1", "TestFighter2"],
                        help="Names for the two test fighters")
    parser.add_argument("--timer",   type=int, default=5,
                        help="Seconds each fighter has to choose a move (default: 5)")
    parser.add_argument("--delay",   type=int, default=3,
                        help="Seconds to pause between rounds (default: 3)")
    parser.add_argument("--port",    type=int, default=8765,
                        help="WebSocket port — must match overlay.js (default: 8765)")
    parser.add_argument("--avatar1", type=str, default="",
                        help="Avatar image URL for fighter 1")
    parser.add_argument("--avatar2", type=str, default="",
                        help="Avatar image URL for fighter 2")
    return parser.parse_args()

async def main():
    args = parse_args()
    name1, name2 = args.fighters

    print(f"[WS] Starting WebSocket server on ws://localhost:{args.port}")
    async with websockets.serve(ws_handler, "localhost", args.port):
        # Run the test fight as a background task so the WS server stays alive
        # until the overlay has had time to show the KO screen and idle return.
        fight_task = asyncio.create_task(
            run_test(
                name1=name1,
                name2=name2,
                avatar1=args.avatar1,
                avatar2=args.avatar2,
                move_timer=args.timer,
                round_delay=args.delay,
            )
        )

        try:
            # Keep the server alive until the fight finishes + 10s buffer
            await fight_task
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Test] Stopped.")