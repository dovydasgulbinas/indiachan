CREATE OR REPLACE FUNCTION user_banned(in_user_id text, in_ban_gt integer, in_ban_lt integer, in_return_ban_reason boolean DEFAULT 'f' )
RETURNS integer AS
$$
DECLARE
	v_ban_ptr_row ban_ptr%ROWTYPE;
        
BEGIN
	SELECT * INTO v_ban_ptr_row FROM ban_ptr WHERE user_id=in_user_id;
	if FOUND THEN
		if v_ban_ptr_row.ban_reason BETWEEN in_ban_gt AND in_ban_lt AND 
		v_ban_ptr_row.ban_till_ts > now() THEN
			if in_return_ban_reason = 'f' THEN
				return 1;
			else
				return v_ban_ptr_row.ban_reason;
			end if;
		end if;			
	end if;
	return 0;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION ban_user(in_user_id text, in_ban_reason integer, in_ban_duration interval, in_ban_post_id integer)
RETURNS integer AS
$$
DECLARE
	v_ban_ptr_row ban_ptr%ROWTYPE;

BEGIN
	SELECT * INTO v_ban_ptr_row FROM ban_ptr WHERE user_id=in_user_id;
	if FOUND THEN
		if v_ban_ptr_row.ban_till_ts > now() THEN

			if in_ban_reason > v_ban_ptr_row.ban_reason THEN
				v_ban_ptr_row.ban_reason = in_ban_reason;
				v_ban_ptr_row.ban_post_id = in_ban_post_id;
			end if;

			UPDATE ban_ptr SET 
			(ban_reason, ban_till_ts, ban_post_id)=(v_ban_ptr_row.ban_reason, v_ban_ptr_row.ban_till_ts + in_ban_duration, v_ban_ptr_row.ban_post_id)
			WHERE user_id=in_user_id;			
		else 
			UPDATE ban_ptr SET 
			(ban_reason, ban_till_ts, ban_post_id)=(in_ban_reason, now() + in_ban_duration, in_ban_post_id)
			WHERE user_id=in_user_id;			
		end if;
		return 2;
	else 		
		INSERT INTO ban_ptr (user_id, ts, ban_till_ts, ban_reason, ban_post_id)
		VALUES (in_user_id, now(), now()+in_ban_duration, in_ban_reason, in_ban_post_id);
		return 1;
	end if;
	return 0;
END;
$$ LANGUAGE plpgsql;



CREATE OR REPLACE FUNCTION start_post ( in_thread_id int, in_user_id text, in_name text, in_text text, in_blob_name text, in_blob_type text, in_blob_info text,
	OUT out_status integer, OUT out_status_text text ) 
AS
$$
DECLARE
	v_posts_by_user integer := 0;
	v_ban_reason integer := 0;
	v_thread_row threads%ROWTYPE;
	v_post_id integer := -1;

	v_temp integer := 0;
	v_posters_increment integer := 0;

BEGIN
	-- 30% probability check to check if user is flooding sv with posts
	if random() < 0.3 THEN
		SELECT count(*) INTO v_posts_by_user FROM posts WHERE user_id=in_user_id AND ts > now() - INTERVAL '15m';
		if v_posts_by_user > 10 THEN
			RAISE NOTICE 'banning user ';
			if ban_user(in_user_id, 1, '10m', NULL) > 0 THEN  -- softban for 10m
				out_status = -1;
				out_status_text = 'Please wait for a while before posting!';
				return;
			end if;
		end if;
	end if;

	PERFORM * FROM threads WHERE post_id=in_thread_id;  -- if thread is valid
	if FOUND THEN
		v_ban_reason = user_banned(in_user_id, 1, 3, 't');

		if v_ban_reason = 0 THEN  -- if not banned
			
			SELECT * INTO v_thread_row FROM threads WHERE post_id=in_thread_id FOR UPDATE;  -- take note of FOR UPDATE
			if FOUND then 
				if v_thread_row.status = 0 AND v_thread_row.post_count < 600 THEN					
					-- ignoring name duplicate check for now TODO	

					-- id | board*() | thread_id* | user_id* | ts | name | text | blob_name | blob_type | blob_info | status		
					INSERT INTO posts (board, thread_id, user_id, name, text, blob_savename, blob_type, blob_info, status) VALUES
					(v_thread_row.board, v_thread_row.post_id, in_user_id, in_name, in_text, in_blob_name, in_blob_type, in_blob_info, 0)
					RETURNING id INTO v_post_id;

					if v_thread_row.bump_ts < now() - INTERVAL '60s'  THEN -- if not bumped recently
						v_thread_row.bump_ts = now();
					end if;

					-- posters_count get
					SELECT COUNT(*) INTO v_temp FROM posts WHERE thread_id=in_thread_id AND user_id=in_user_id;
					if v_temp = 1 THEN  -- SELECT FOR UPDATE above was done because of this :)
						v_posters_increment = 1;
					end if;

					UPDATE threads SET (bump_ts, post_count, posters_count)=(v_thread_row.bump_ts, post_count+1, posters_count + v_posters_increment)
					WHERE post_id = in_thread_id;

					out_status = v_post_id;
				else
					out_status = -1;
					out_status_text = 'you can''t post in this thread anymore';
				end if;
			else
				out_status = -1;
				out_status_text = 'Thread does not exist';
			end if;
			
		elsif v_ban_reason = 1 THEN -- if soft banned
			out_status = -1;
			out_status_text = 'Please wait for a while before posting.';
		elsif v_ban_reason > 1 THEN -- if hard banned
			out_status = -1;
			out_status_text = 'banned';
		end if;
	else
		out_status = -1;
		out_status_text = 'mongodb exception : no variable ''id'' in line 23'; -- joke
	end if;

END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION start_thread ( in_board text, in_user_id text,
	in_name text, in_title text, in_text text, in_blob_name text, in_blob_type text, in_blob_info text,
	OUT out_status integer, OUT out_status_text text ) 
AS
$$
DECLARE
	v_threads_created_by_user integer := 0;
	v_ban_reason integer := 0;
	v_post_id integer := 0;

	v_last_thread_post_id_arr integer[];
	v_idee integer;
	
BEGIN
	-- check if board is valid	
	PERFORM * FROM boards WHERE board=in_board; 
	if FOUND THEN

		v_ban_reason = user_banned(in_user_id, 1, 3, 't');
		if v_ban_reason = 0 THEN  -- if not banned
			
			-- no of posts created by this user in last 60 min
			SELECT count(post_id) INTO v_threads_created_by_user FROM threads WHERE 
			user_id=in_user_id AND board=in_board AND ts > now() - INTERVAL'60m'; 

			if v_threads_created_by_user <= 2 THEN  -- max 3 threads allowed
				
				INSERT INTO posts (board, thread_id, user_id, name, text, blob_savename, blob_type, blob_info, status) VALUES
				(in_board, currval('posts_id_seq'), in_user_id, in_name, in_text, in_blob_name, in_blob_type, in_blob_info, 0)
				RETURNING id INTO v_post_id;

				-- post_id () | board* | user_id | ts | title | post_count | posters_count | bump_ts | status
				INSERT INTO threads (post_id, board, user_id, title, post_count, posters_count, bump_ts, status ) VALUES
				( v_post_id, in_board, in_user_id, in_title, 1, 1, now(), 0 );

				-- marking last thread and the post as 1 ( removed naturally status = 1 )
				v_last_thread_post_id_arr = array( SELECT post_id FROM threads WHERE board=in_board AND status = 0 ORDER BY bump_ts DESC OFFSET 100 );
				FOREACH v_idee IN ARRAY v_last_thread_post_id_arr
				LOOP
					UPDATE threads SET status = 1 WHERE post_id = v_idee;
					UPDATE posts SET status = 1 WHERE id = v_idee;
				END LOOP;
				
				out_status = v_post_id;
			else
				out_status = -1;
				out_status_text = 'Please create a new thread after some time.';
			end if;	
			

		elsif v_ban_reason = 1 THEN -- if soft banned
			out_status = -1;
			out_status_text = 'Please wait for a while before posting.';
		elsif v_ban_reason > 1 THEN -- if hard banned
			out_status = -1;
			out_status_text = 'banned';
		end if; 
		
	else
		out_status = -1;
		out_status_text = 'mongodb exception : no variable id in line 24'; -- joke
	end if;	
END;
$$ LANGUAGE plpgsql;


-- post_id, ts, bump_ts, reply_count, title, text, blobx3 fields
-- 
CREATE OR REPLACE FUNCTION get_catalog( in_board text )
RETURNS TABLE (post_id int, ts double precision, bump_ts double precision, reply_count int, title text, 
		txt text, blob_savename text, blob_type text, blob_info text )
AS 
$$
BEGIN	
	RETURN QUERY SELECT threads.post_id, extract(epoch from threads.ts), extract(epoch from threads.bump_ts), threads.post_count, threads.title, posts.text,
 posts.blob_savename, posts.blob_type, posts.blob_info FROM threads INNER JOIN posts ON posts.id=threads.post_id
 WHERE threads.board=in_board AND threads.status=0 ORDER BY threads.bump_ts DESC;
END;
$$ LANGUAGE plpgsql;


/*
	returns rows of the posts table
	note : the ts column changed to utc in posts_utc
*/
CREATE OR REPLACE VIEW posts_utc AS SELECT id, board, thread_id, user_id, 
extract(epoch from ts) AS utc, name, text, 
blob_savename, blob_type, blob_info, status FROM posts;



CREATE OR REPLACE FUNCTION get_post( in_board text, in_thread_id integer )
RETURNS SETOF posts_utc
AS
$$
BEGIN	
	RETURN QUERY SELECT * FROM posts_utc WHERE board=in_board AND thread_id=in_thread_id ORDER BY utc;

END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION get_update( in_thread_id integer, in_last_id integer )
RETURNS SETOF posts_utc
AS
$$
DECLARE	
	v_last_id_utc double precision := 0;
BEGIN	
	SELECT utc INTO v_last_id_utc FROM posts_utc WHERE id=in_last_id AND thread_id=in_thread_id;
	
	RETURN QUERY SELECT * FROM posts_utc WHERE thread_id=in_thread_id AND utc>=v_last_id_utc ORDER BY utc;

END;
$$ LANGUAGE plpgsql;


CREATE OR REPLACE FUNCTION report_post( in_user_id text,
	in_thread_id integer, in_post_id integer, in_report_reason integer,
	OUT out_status integer, OUT out_status_text text )
AS
$$
DECLARE
	v_posts_row posts%ROWTYPE;
	v_threads_row threads%ROWTYPE;

	v_reportsrc_row report_src%ROWTYPE;

	v_ban_reason integer := 0;
	v_rabid_report_count integer := 0;

	v_post_deletable integer := 0;
	v_delete_threshold integer := 1000;  -- previously this number was 4, but changed it to large number because of abuse

	v_1_report_count integer := 0;
	v_2_report_count integer := 0;

	v_temp integer:= 0;

	v_delete_status_to_set integer := 2;  -- default is deleted by other users. will be set to 4 if reporter is same as poster
BEGIN
	-- if user not banned
	-- captcha finalized
	-- post_id exists and not deleted and thread_exists and not deleted
	-- user_id not rabid reporting
	-- user_id not already reported for the post_id

	v_ban_reason = user_banned(in_user_id, 1, 3, 't');

	if v_ban_reason = 0 THEN  -- if not banned		

		SELECT * INTO v_posts_row FROM posts WHERE id = in_post_id AND thread_id=in_thread_id;

		if FOUND THEN 
			SELECT * INTO v_threads_row FROM threads WHERE post_id=v_posts_row.thread_id;

			if v_posts_row.status = 0 AND v_threads_row.status = 0 THEN -- if they aren't deleted already
				SELECT COUNT(*) INTO v_rabid_report_count FROM report_src WHERE reporter_id=in_user_id AND ts > now() - INTERVAL '10m';
				if v_rabid_report_count < 5 THEN -- if no rabid report
					
					PERFORM * FROM report_src WHERE reporter_id=in_user_id AND post_id=in_post_id;  -- already reported check
					if NOT FOUND THEN 
						-- all checks passed. report request is processable now

						if v_posts_row.user_id=in_user_id THEN  -- if poster himself is the reporter							 	
						 	INSERT INTO report_src (reporter_id, post_id, reported_id, reason, consumed)
						 	VALUES (in_user_id, in_post_id, v_posts_row.user_id, in_report_reason, 't');

							v_post_deletable = 1;
							v_delete_status_to_set = 4;
							out_status_text = 'delete';
						else
							INSERT INTO report_src (reporter_id, post_id, reported_id, reason, consumed)
						 	VALUES (in_user_id, in_post_id, v_posts_row.user_id, in_report_reason, 'f');

						 	FOR v_reportsrc_row IN SELECT * FROM report_src WHERE post_id=in_post_id AND consumed = 'f'
						 	LOOP
						 		if v_reportsrc_row.reason = 1 THEN 
						 			v_1_report_count := v_1_report_count + 1;
						 		else
						 			v_2_report_count := v_2_report_count + 1;
						 		end if;
						 	END LOOP;

						 	if v_1_report_count+v_2_report_count >= v_delete_threshold THEN 
						 		if v_posts_row.id != v_posts_row.thread_id THEN -- if not op 
						 			v_post_deletable = 1; 
						 		else 										-- threshold check for op post
						 			--SELECT COUNT(DISTINCT user_id) INTO v_temp FROM posts WHERE thread_id=v_posts_row.thread_id;
						 			SELECT posters_count INTO v_temp FROM threads WHERE post_id=v_posts_row.thread_id;
						 			v_delete_threshold = v_delete_threshold + v_temp/5;	
						 			if v_1_report_count + v_2_report_count >= v_delete_threshold THEN
						 				v_post_deletable = 1;
						 			end if;						 			
						 		end if;

						 		if v_post_deletable = 1 THEN							 			
							 		v_ban_reason = 2;  -- reusing variable and setting default to reason 2 ( spam )
							 		if v_2_report_count >= v_1_report_count THEN
							 			v_ban_reason = 3; -- set to 3 ( illegal/improper content )
							 		end if;

							 		UPDATE report_src SET consumed='t' WHERE  post_id=in_post_id AND consumed = 'f';

							 		PERFORM ban_user( v_posts_row.user_id, v_ban_reason, '30m', v_posts_row.id ); -- ban the dst here
						 		end if;

						 	end if;

						end if;


						if v_post_deletable = 1 THEN
							if v_posts_row.id=v_posts_row.thread_id THEN -- if op 
								UPDATE threads SET status=v_delete_status_to_set WHERE post_id=in_post_id; -- status=2 for deleted by users themselves
							end if;

							UPDATE posts SET status=v_delete_status_to_set WHERE id=in_post_id;  -- post deleted by poster will have status = 1
						end if;

						out_status = 1;  -- all good

					else
						out_status = -1;
						out_status_text = 'you have already reported for this post.';
						return;
					end if;


				else
					if ban_user(in_user_id, 1, '2m', NULL) > 0 THEN  -- softban for 2m
						out_status = -1;
						out_status_text = 'Please wait for a while before posting.';
						return;
					end if;
				end if;
			else
				out_status = -1;
				out_status_text = 'post does not exist.';
			end if;

		else
			out_status = -1;
			out_status_text = 'post does not exist';
		end if;

		
	elsif v_ban_reason = 1 THEN
		if ban_user(in_user_id, 1, '1m', NULL) > 0 THEN  -- softban for 1m
			out_status = -1;
			out_status_text = 'Please wait for a while before posting!';
			return;
		end if;
	elsif v_ban_reason > 1 THEN -- if hard banned
		out_status = -1;
		out_status_text = 'banned';
	end if;

END;
$$ LANGUAGE plpgsql;

