import json
import threading
import unittest
import urllib.error
import urllib.request

from server.app import GomokuServer, Handler, rooms, subscribers


class ServerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = GomokuServer(("127.0.0.1", 0), Handler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        rooms.clear()
        subscribers.clear()

    def request(self, path, body=None, session=None):
        headers = {}
        method = "GET"
        data = None
        if body is not None:
            method = "POST"
            headers["Content-Type"] = "application/json"
            data = json.dumps(body).encode()
        if session:
            headers["X-Player-Id"] = session["playerId"]
            headers["X-Player-Token"] = session["playerToken"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def create_room(self, mode="normal"):
        status, result = self.request("/api/rooms", {"name": "房主", "mode": mode})
        self.assertEqual(status, 201)
        return result

    def test_full_room_rejects_third_player(self):
        created = self.create_room()
        code = created["room"]["code"]
        self.assertEqual(self.request(f"/api/rooms/{code}/join", {"name": "白方"})[0], 200)
        status, result = self.request(f"/api/rooms/{code}/join", {"name": "第三人"})
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "ROOM_FULL")

    def test_host_cannot_start_until_white_joins(self):
        created = self.create_room()
        code = created["room"]["code"]
        status, result = self.request(f"/api/rooms/{code}/start", {}, created)
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "NOT_READY")

    def test_server_accepts_authoritative_move_and_rejects_wrong_turn(self):
        created = self.create_room("professional")
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        _, started = self.request(f"/api/rooms/{code}/start", {}, created)
        room = started["room"]
        status, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 7, "expectedVersion": room["version"]},
            created,
        )
        self.assertEqual(status, 200)
        self.assertEqual(moved["room"]["game"]["board"][7 * 15 + 7], 1)
        status, result = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 8, "expectedVersion": moved["room"]["version"]},
            created,
        )
        self.assertEqual(status, 422)
        self.assertEqual(result["error"], "ILLEGAL_MOVE")
        self.assertTrue(joined["playerToken"])

    def test_stale_version_is_rejected(self):
        created = self.create_room()
        code = created["room"]["code"]
        self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        _, started = self.request(f"/api/rooms/{code}/start", {}, created)
        status, result = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 7, "expectedVersion": started["room"]["version"] - 1},
            created,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["error"], "STALE_STATE")

    def test_players_can_confirm_seat_swap_before_start(self):
        created = self.create_room()
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})

        status, requested = self.request(f"/api/rooms/{code}/swap", {}, created)
        self.assertEqual(status, 200)
        self.assertEqual(requested["room"]["seatSwapRequestPlayerId"], created["playerId"])

        status, swapped = self.request(f"/api/rooms/{code}/swap", {}, joined)
        self.assertEqual(status, 200)
        colors = {player["id"]: player["color"] for player in swapped["room"]["players"]}
        self.assertEqual(colors[created["playerId"]], 2)
        self.assertEqual(colors[joined["playerId"]], 1)

        status, started = self.request(f"/api/rooms/{code}/start", {}, created)
        self.assertEqual(status, 200)
        self.assertEqual(started["room"]["game"]["currentColor"], 1)

    def test_players_can_confirm_seat_swap_after_game_finished(self):
        created = self.create_room()
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        self.request(f"/api/rooms/{code}/start", {}, created)
        self.request(f"/api/rooms/{code}/resign", {}, created)

        self.assertEqual(self.request(f"/api/rooms/{code}/swap", {}, joined)[0], 200)
        status, swapped = self.request(f"/api/rooms/{code}/swap", {}, created)
        self.assertEqual(status, 200)
        self.assertEqual(swapped["room"]["status"], "playing")
        colors = {player["id"]: player["color"] for player in swapped["room"]["players"]}
        self.assertEqual(colors[created["playerId"]], 2)
        self.assertEqual(colors[joined["playerId"]], 1)
        self.assertEqual(swapped["room"]["game"]["currentColor"], 1)

    def test_only_opponent_can_undo_last_move_without_limit(self):
        created = self.create_room()
        code = created["room"]["code"]
        _, joined = self.request(f"/api/rooms/{code}/join", {"name": "白方"})
        _, started = self.request(f"/api/rooms/{code}/start", {}, created)
        room = started["room"]

        _, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 7, "expectedVersion": room["version"]},
            created,
        )
        _, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 7, "col": 8, "expectedVersion": moved["room"]["version"]},
            joined,
        )
        _, moved = self.request(
            f"/api/rooms/{code}/place",
            {"row": 8, "col": 7, "expectedVersion": moved["room"]["version"]},
            created,
        )

        status, result = self.request(f"/api/rooms/{code}/undo", {}, created)
        self.assertEqual(status, 403)
        self.assertEqual(result["error"], "UNDO_NOT_OPPONENT")

        status, undone = self.request(f"/api/rooms/{code}/undo", {}, joined)
        self.assertEqual(status, 200)
        game = undone["room"]["game"]
        self.assertEqual(len(game["moveHistory"]), 2)
        self.assertEqual(game["board"][7 * 15 + 7], 1)
        self.assertEqual(game["currentColor"], 1)
        self.assertEqual(game["turn"], 3)

        _, moved_again = self.request(
            f"/api/rooms/{code}/place",
            {"row": 8, "col": 7, "expectedVersion": undone["room"]["version"]},
            created,
        )
        status, undone_again = self.request(f"/api/rooms/{code}/undo", {}, joined)
        self.assertEqual(status, 200)
        self.assertEqual(len(undone_again["room"]["game"]["moveHistory"]), 2)
        self.assertEqual(moved_again["room"]["game"]["moveHistory"][-1]["color"], 1)


if __name__ == "__main__":
    unittest.main()
