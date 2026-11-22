-- Synthetic records only; no production database or upstream download.
CREATE TABLE receiving_game_source (
    game_id VARCHAR,
    player_id VARCHAR,
    targets INTEGER,
    receptions INTEGER,
    receiving_yards INTEGER
);
INSERT INTO receiving_game_source VALUES
    ('example-game-1', 'receiver-a', 1, 1, 10),
    ('example-game-2', 'receiver-a', 9, 1, 30),
    ('example-game-1', 'receiver-b', 4, 3, 24);
