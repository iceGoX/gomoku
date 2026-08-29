import unittest

from server.game_engine import BLACK, WHITE, analyze_move, create_game, place_stone


def board_with(points, color=BLACK):
    game = create_game("professional")
    for row, col in points:
        game["board"][row * 15 + col] = color
    return game["board"]


class GameEngineTests(unittest.TestCase):
    def test_professional_black_first_move_must_be_center(self):
        game = create_game("professional")
        self.assertFalse(place_stone(game, BLACK, 6, 7)[0])
        self.assertTrue(place_stone(game, BLACK, 7, 7)[0])

    def test_normal_mode_allows_any_first_move(self):
        game = create_game("normal")
        self.assertTrue(place_stone(game, BLACK, 0, 0)[0])

    def test_black_overline_is_forbidden(self):
        board = board_with([(7, col) for col in range(2, 7)])
        result = analyze_move(board, 7, 7, BLACK, "professional")
        self.assertFalse(result["legal"])
        self.assertEqual(result["code"], "OVERLINE")

    def test_black_double_four_is_forbidden(self):
        board = board_with([(7, 5), (7, 6), (7, 8), (5, 7), (6, 7), (8, 7)])
        result = analyze_move(board, 7, 7, BLACK, "professional")
        self.assertFalse(result["legal"])
        self.assertEqual(result["code"], "DOUBLE_FOUR")

    def test_black_double_three_is_forbidden(self):
        board = board_with([(7, 6), (7, 8), (6, 7), (8, 7)])
        result = analyze_move(board, 7, 7, BLACK, "professional")
        self.assertFalse(result["legal"])
        self.assertEqual(result["code"], "DOUBLE_THREE")

    def test_exact_five_wins_for_black(self):
        game = create_game("professional")
        for col in range(3, 7):
            game["board"][7 * 15 + col] = BLACK
        success, _ = place_stone(game, BLACK, 7, 7)
        self.assertTrue(success)
        self.assertEqual(game["winnerColor"], BLACK)

    def test_white_overline_wins(self):
        game = create_game("professional")
        game["currentColor"] = WHITE
        for col in range(2, 7):
            game["board"][7 * 15 + col] = WHITE
        success, _ = place_stone(game, WHITE, 7, 7)
        self.assertTrue(success)
        self.assertEqual(game["winnerColor"], WHITE)

    def test_normal_mode_overline_wins_for_black(self):
        game = create_game("normal")
        for col in range(2, 7):
            game["board"][7 * 15 + col] = BLACK
        success, _ = place_stone(game, BLACK, 7, 7)
        self.assertTrue(success)
        self.assertEqual(game["winnerColor"], BLACK)


if __name__ == "__main__":
    unittest.main()
