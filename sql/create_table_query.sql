CREATE TABLE IF NOT EXISTS boards (
    board text PRIMARY KEY,
    parent_board text REFERENCES boards(board),
    level int,  -- not used yet. A stub.
    administrative_region text,  -- not used yet. A stub.
    extra_text text,
    display_name text
);

CREATE INDEX boards_parent_idx ON boards(parent_board);
CREATE INDEX boards_level_idx ON boards(level);


CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    board text REFERENCES boards(board) NOT NULL,  -- add index
    thread_id int NOT NULL,  -- add index
    user_id text NOT NULL,  -- add index
    ts timestamp with time zone default (now() at time zone 'utc'),
    name text NOT NULL,
    text text,    
    blob_savename text,
    blob_type text,
    blob_info text,  -- filename img_size file_size
    status int
);

CREATE INDEX posts_board_idx ON posts (board);
CREATE INDEX posts_thread_idx ON posts (thread_id);
CREATE INDEX posts_user_idx ON posts (user_id);

ALTER SEQUENCE posts_id_seq RESTART WITH 100;


CREATE TABLE IF NOT EXISTS threads (
    post_id int REFERENCES posts(id),
    board text REFERENCES boards(board) NOT NULL,   -- add index
    user_id text NOT NULL,
    ts timestamp with time zone default (now() at time zone 'utc'),
    title text,
    post_count int NOT NULL,
    posters_count int NOT NULL,
    bump_ts timestamp with time zone NOT NULL,
    status int
);

CREATE INDEX threads_board_idx ON threads (board);


CREATE TABLE IF NOT EXISTS report_src (
    id SERIAL PRIMARY KEY,
    reporter_id text NOT NULL,  -- add index
    post_id int NOT NULL,  -- add index
    ts timestamp with time zone default (now() at time zone 'utc'),
    reported_id text NOT NULL,
    reason int NOT NULL,
    consumed boolean NOT NULL
);

CREATE INDEX reportsrc_idsrc_idx ON report_src (reporter_id);
CREATE INDEX reportsrc_postid_idx ON report_src (post_id);


CREATE TABLE IF NOT EXISTS ban_ptr (
    user_id text PRIMARY KEY,
    ts timestamp with time zone default (now() at time zone 'utc'),
    ban_till_ts timestamp with time zone default (now() at time zone 'utc'),
    ban_reason int NOT NULL,
    ban_post_id int
);



