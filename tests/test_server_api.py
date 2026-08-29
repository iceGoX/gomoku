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


if __name__ == "__main__":
    unittest.main()
