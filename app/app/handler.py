#!/usr/bin/env python
# coding: utf-8 -*- 

import psycopg2
import psycopg2.extensions
psycopg2.extensions.register_type(psycopg2.extensions.UNICODE)
psycopg2.extensions.register_type(psycopg2.extensions.UNICODEARRAY)

import time
from datetime import datetime
import re
import os
from app import app # circular import sorta

from flask import render_template, jsonify, request
from imageHandler import ImageHandler

import base64, hashlib

from PIL import Image

class Handler:

	def __init__ (self) : 
		self.con = psycopg2.connect("dbname='indiach_db' user='indiach_role'")

	def __del__ (self) :
		if self.con :
			self.con.close()
	

	def handle_catalog(self, board_name ):
		cur = self.con.cursor()

		cur.execute("SELECT * FROM boards WHERE board=%s", (board_name,) )
		res = cur.fetchall()

		if not res :
			return render_template('404.html'), 404

		board_row = res[0]

		#preparing board_info vars
		board_display_name = board_row[5]
		board_level = board_row[2]
		board_extra_text = board_row[4]
		if board_extra_text == None :
			board_extra_text = ''

		if board_level == 1 and len(board_name) <= 4 :
			board_display_name = '/%s/ - %s' %(board_name, board_display_name)


		cur.execute("SELECT * FROM get_catalog(%s)", (board_name,) )
		res = cur.fetchall()

		div_list = []

		#post_id, ts, bump_ts, post_count, title, text, blobx3 fields
		for row in res:
			post_id, ts_utc, bump_ts_utc, post_count, title, text, blob_savename, blob_filetype, blob_info = row
			imgname, imgsize, filesize = blob_info.split(' ')

			if len(text) > 170 :
				text =  '%s(...)'  %text[:165]
			
			text = Handler.single_linify( text ) # html escape is done by Jinja itself so dont worry about that

			
			href = '/boards/%s/thread/%s' %(board_name,post_id)

			b = {'ts' : int(ts_utc), 'bump_ts' : int(bump_ts_utc), 
				'href':href, 'filesize': filesize, 'savename' : blob_savename, 'title':title, 'text' : text, 'reply_count':(post_count-1) }

			div_list.append(b)

		board_info = {
		'board_name' : board_name,
		'board_display_name' : board_display_name,
		'board_extra_text' : board_extra_text
		}

		return render_template('catalog.html', board_info=board_info, div_list=div_list)


	# todo add check if board_name exists or not ( while retrieving board_list itself )
	# todo add text len limit for text ( trim and trim again )
	
	def handle_post(self, board_name, thread_id) :
                user_id = Handler.userId()

		cur = self.con.cursor()
		cur.execute("SELECT * FROM threads INNER JOIN boards ON threads.board=boards.board "\
			"WHERE post_id=%s AND threads.board=%s AND status=0", 
			(thread_id,board_name) )
		res = cur.fetchall()

		if not res :
			return render_template('404.html'), 404

		#preparing board_info vars
		thread_row = res[0]
		post_title = Handler.wbrify_line(Handler.html_escape( thread_row[4] ))
		post_count = thread_row[5]
		posters_count = thread_row[6]
		back_link = '/boards/%s' %board_name

		board_display_name = thread_row[9+5]
		board_level = thread_row[9+2]		

		if board_level == 1 and len(board_name) <= 4 :
			board_display_name = '/%s/ - %s' %(board_name, board_display_name)

		page_title = '%s - %s' %(board_display_name, post_title)

		#preparing posts stuff
		cur.execute("SELECT * FROM get_post(%s, %s)", (board_name, thread_id) )
		res = cur.fetchall()

                you_list = []
                you = False
		innards = []

		op_row = res[0]		
		op = Handler.get_post_obj(op_row)
		op['title'] = post_title

		if op['user_id'] == user_id:
			you_list.append( op['post_id'] )
                        you = True
		innards.append( Handler.get_post_html(op, you) )

		for row in res[1:] :
                        you = False  # make sure to disable it for each item by default
			p = Handler.get_post_obj(row)
			if p['user_id'] == user_id :
				you_list.append( p['post_id'] )
                                you = True

			innards.append( Handler.get_post_html(p, you) )


		board_info =  {
		'board_name' : board_name,
		'thread_id' : thread_id,
		'reply_count' : post_count-1,
		'posters_count' : posters_count,
		'back_link' : back_link,
		'board_display_name' : board_display_name,
		'page_title' : page_title
		}

		return render_template( 'post.html', board_info=board_info, innards=innards, you_list=you_list.__str__() )

	def handle_banned(self) :
		user_id = Handler.userId()

		cur = self.con.cursor()
		cur.execute("SELECT * FROM user_banned(%s, 1, 3, 't');" , (user_id,) )
		res = cur.fetchall()
		row = res[0]

		msg = 'You are not banned.'
		banned = ''

		if row[0] == 2 :
			msg = 'You are banned for spamming/flooding. Please check again later to see your ban status.'
			banned = 'banned'
		if row[0] == 3 :
			msg = 'You are banned for posting inappropriate content. Please check again later to see your ban status.'
			banned = 'banned'	

		return render_template('banned.html', msg=msg, banned=banned )





	def handle_start_thread(self) :
		board_name = request.form['board_name']

		name = Handler.single_linify(request.form['name']).strip()
		subject = Handler.single_linify(request.form['subject']).strip()
		text, text_line_count = Handler.clean_post_message(request.form['text'])

		if len(name) > 50 or len(subject) > 100 or len(text) > 1500 or text_line_count > 40 :			
			return 'bad request', 400   # TODO can hard ban him here for 1 entire day	

		if len(text) == 0 and len(subject) == 0 :
			return 'empty content', 400  # bannable again

		if not request.files :
			return 'no image attached', 400

		img_handler = ImageHandler(request.files['image'])

		img_verify_result = img_handler.verify_image(app.config['UPLOAD_FOLDER'])

		if img_verify_result != 1 :
			return img_verify_result

		# saving 
		user_id = Handler.userId()
		blob_name = img_handler.savename_utc
		blob_type = img_handler.save_type
		blob_info = '%s %s %s' %( img_handler.filename, img_handler.img_size, 'x'.join( str(v) for v in img_handler.size) )	

		if len(name) == 0 :
			name = 'Anonymous'

		cur = self.con.cursor()

		# in_board varchar, in_user_id inet, in_name varchar, in_title varchar, in_text varchar, in_blob_name varchar, in_blob_type varchar, in_blob_info varchar,
		cur.execute("SELECT * FROM start_thread(%s, %s, %s, %s, %s, %s, %s, %s);" , 
			(board_name, user_id, name, subject, text, blob_name, blob_type, blob_info) )		

		res = cur.fetchall()
		row = res[0]

		#note : these two commands should be in this order
		if row[0] > 0 :  # save if all good from db
			img_handler.save_image()

		self.con.commit()  #commit the statement ( even if status < 0 because ban might have happened )

		if row[0] <= 0 :			
			return row[1], 400

		post_id = row[0]
		redirect_url = '/boards/%s/thread/%s' %(board_name, post_id)

		#return 'post created : %s' %(post_id)
		returnable = {'post_id' : post_id, 'redirect_url' : redirect_url}
		return jsonify(returnable)

		'''
		http://flask.pocoo.org/docs/0.11/patterns/fileuploads/
		http://werkzeug.pocoo.org/docs/0.11/datastructures/#werkzeug.datastructures.FileStorage
		http://pillow.readthedocs.io/en/3.1.x/reference/Image.html#PIL.Image.Image.seek
		http://pillow.readthedocs.io/en/3.1.x/reference/Image.html#PIL.Image.Image.save

		http://flask.pocoo.org/docs/0.11/patterns/packages/
		'''

	def handle_add_post(self) :
		thread_id = request.form['thread_id']
		name = Handler.single_linify(request.form['name']).strip()
		text, text_line_count = Handler.clean_post_message(request.form['text'])

		blob_name = blob_type = blob_info = None

		image_exists = False
		img_handler = None		

		try :
			thread_id = int( thread_id )
		except ValueError :
			return 'Major server malfunction. Overheat detected.', 400

		if len(name) > 50 or len(text) > 1500 or text_line_count > 40:
			return 'bad request' , 400   # TODO can hard ban him here for 1 entire day			

		if request.files and request.files['image'] :
			image_exists = True
			img_handler = ImageHandler(request.files['image'])
			img_verify_result = img_handler.verify_image(app.config['UPLOAD_FOLDER'])		
			if img_verify_result != 1 :
				return img_verify_result
			blob_name = img_handler.savename_utc
			blob_type = img_handler.save_type
			blob_info = '%s %s %s' %( img_handler.filename, img_handler.img_size, 'x'.join( str(v) for v in img_handler.size) )

		if len(text) == 0 and image_exists == False :
			return 'empty content', 400  # bannable again

		# saving
		user_id = Handler.userId()
		if len(name) == 0 :
			name = 'Anonymous'

		cur = self.con.cursor()

		cur.execute("SELECT * FROM start_post(%s, %s, %s, %s, %s,  %s, %s )",
			(thread_id, user_id, name, text, blob_name, blob_type, blob_info) )

		res = cur.fetchall()
		row = res[0]

		if image_exists == True and row[0] > 0 : #if image uploaded and all good from db
			img_handler.save_image()
		self.con.commit()

		if row[0] <= 0 :
			return row[1], 400

		post_id = row[0]

		return 'post created : %s' %(post_id)

	def handle_update_post(self) :
		thread_id = request.form['thread_id']
		last_id = request.form['last_id']
		user_id = Handler.userId()

		try :
			thread_id = int( thread_id )
			last_id = int( last_id )
		except ValueError :
			return 'Major server malfunction. Overheat detected.', 400

		#db work. check if thread exists and is not deleted

		cur = self.con.cursor()
		cur.execute("SELECT status, posters_count, post_count FROM threads WHERE post_id=%s", (thread_id,) )
		threads_res = cur.fetchall()

		if not threads_res :
			return 'error', 404  # thread_id not valid
		threads_row = threads_res[0]

		thread_status = threads_row[0]
		thread_posters_count = threads_row[1]
		thread_reply_count = threads_row[2] - 1

		if thread_status != 0 :
			return 'thread was pruned or deleted', 404

		cur.execute( "SELECT * FROM get_update(%s,%s)", (thread_id,last_id) )
		res = cur.fetchall()

		you_list = []
                you = False
		posts = []

		f = 0  # first row to consider
		if res[0][0] == last_id :
			f = 1
		for row in res[f:] :
			p = Handler.get_post_obj(row)
			if p['user_id'] == user_id :
				you_list.append( p['post_id'] )
                                you = True
			posts.append( Handler.get_post_html(p, you, True) )

		to_return = {'you_list' : you_list, 'posts' : posts, 'posters_count' : thread_posters_count, 'reply_count' : thread_reply_count}

		return jsonify(to_return)




	def handle_report_post( self ) :

		thread_id = request.form['thread_id']
		post_id = request.form['post_id']
		reason = request.form['reason'].strip()		

		try :
			thread_id = int( thread_id )
			post_id = int( post_id )
		except ValueError :
			return 'Major server malfunction. Overheat detected.', 400


		if reason != 'spam' and reason != 'illegal' :
			return '%s is not a valid reason' %reason, 400

		reason = 1 if reason == 'spam' else 2

		user_id = Handler.userId()

		#all good. saving
		cur = self.con.cursor()		
		cur.execute("SELECT * FROM report_post(%s, %s, %s, %s );" , (user_id, thread_id, post_id, reason) )
		self.con.commit()

		res = cur.fetchall()
		row = res[0]

		if row[0] <= 0 :
		    return row[1], 400

                if row[1] == 'delete' :
                    return 'deleted post No.%s' %post_id
                else :		
        	    return 'report submitted for post No.%s' %post_id


	@staticmethod
	def get_post_html( post_obj, you, get_inside_only=False ) :

		op_file_info_title_fmt = u"<span class='bold title'>{} </span>"		
		
		#post_div_fmt = u"<div class='post_container'> <div class='post {}' id='p{}'>{}</div> </div>"
		post_div_container_fmt = u"<div class='post_container'>{}</div>"
		post_div_inside_fmt = u"<div class='post {}' id='p{}'>{}</div>"

		post_info_fmt = 	u"<div class='post_info'> {} " \
					"<span class='bold name'>{} </span>" \
                                        "{}" \
					"<span class='small ts' data-utc='{}'>{} </span>"\
					"<button class='report_button small'>{}</button> " \
					"<button class='hide_button small'></button> " \
					"<span><a href='#p{}'>No.</a><a class='post_num'>{}</a></span>" \
					"<span class='qbl small' id='qbl{}'><span> Quoted&nbsp;By: </span></span>" \
					"</div>"

		file_stuff_fmt = u"<div class='file_info small'>" \
						"File: <a href='/static/images/{}' target='_blank'>{}</a>" \
						" ({}, {})" \
						"</div>" \
						"<a class='file_thumb' href='/static/images/{}' target='_blank'>" \
						"<img src='/static/images/{}' alt='{}'/>" \
						"</a>"

		post_msg_fmt = u"<blockquote class='post_message'>{}</blockquote>"
		post_msg_deleted_fmt = u"<blockquote class='post_message deleted'>{}</blockquote>"

		## building actual html here
		
		post_deleted = post_obj['deleted']
		is_op = post_obj['is_op']
		title = post_obj['title'] if is_op else ''

		blob_savename = blob_savename_s = blobname = None
		if 'blob_savename' in post_obj : 
			blob_savename = post_obj['blob_savename']
			blob_savename_s = post_obj['blob_savename_s']
			blobname = post_obj['blobname']
			blob_size = post_obj['blob_size']
			blob_dim = post_obj['blob_dim']
		
		name = post_obj['name']
		text = post_obj['text']
		time = post_obj['time']
		utc  = post_obj['utc']
		post_id = post_obj['post_id']

                if post_deleted :
                    if post_obj['status'] == 4 :
                        post_msg = post_msg_deleted_fmt.format('[post deleted by submitter]')
                    else :
                        post_msg = post_msg_deleted_fmt.format('[post deleted]')
                else :
                    post_msg = post_msg_fmt.format(post_obj['text'])

		file_info = '' if ( post_deleted or blob_savename is None ) else file_stuff_fmt.format(
			blob_savename, blobname, blob_size, blob_dim, blob_savename, blob_savename_s, blob_size	)

		title_span = op_file_info_title_fmt.format(title) if is_op else ''
                poster_uid_span = "<span class='poster_uid'> (ID:&nbsp;<span>&nbsp;{}&nbsp;</span>) </span>".format(post_obj['poster_uid'])
                report_button_txt = 'delete' if you else 'report'

		post_info = post_info_fmt.format( title_span, name, poster_uid_span, utc, time, report_button_txt, post_id, post_id, post_id )

		op_post_class = "op_post" if is_op else ''

		inn = [post_info, file_info, post_msg]

		post_div_inside = post_div_inside_fmt.format(op_post_class, post_id, ''.join( inn ))

		if get_inside_only == True :
			return post_div_inside
		else :
			return post_div_container_fmt.format( post_div_inside )

        @staticmethod
        def getPosterUid(user_id, board, thread_id) :
            c = '{}|{}|{}'.format(user_id,board,thread_id)
            m = hashlib.md5()
            m.update(c)
            return base64.b64encode( m.digest() )[0:8]		

	@staticmethod
	def get_post_obj( row ) :
		post_obj = {}
		post_obj['post_id'] = row[0]
		post_obj['board'] = row[1]
		post_obj['thread_id'] = row[2]
		post_obj['user_id'] = row[3]

		utc = int(row[4])

		post_obj['time'] = datetime.utcfromtimestamp(utc + 19800).strftime("%d/%m/%Y(%a)%H:%M:%S")
		post_obj['utc'] = utc

		post_obj['name'] = Handler.wbrify_line(Handler.html_escape(row[5]))
		post_obj['text'] = Handler.format_post_message( row[6] )

                post_obj['status'] = row[10]
		post_obj['deleted'] = row[10] > 0
		post_obj['is_op'] = row[2] == row[0]

                post_obj['poster_uid'] = Handler.getPosterUid(post_obj['user_id'], post_obj['board'], post_obj['thread_id'])

		if row[7]:
			post_obj['blob_savename'] = "%s.%s"  %(row[7], row[8])
			post_obj['blob_savename_s'] = "%s_s.%s"  %(row[7], 'jpg')
			blobname, post_obj['blob_size'], post_obj['blob_dim'] = row[9].split(' ')
			blobname = Handler.html_escape( '%s.%s' %(blobname, row[8]) )
			post_obj['blobname'] = (blobname[:30] + '(...)') if len(blobname)>35 else blobname

		return post_obj

	@staticmethod
	def clean_post_message(text):
		text = text.strip()

		lines = []
		for line in text.splitlines():
			lines.append(line.strip())

		line_count = len(lines)
		return '\n'.join(lines), line_count

	@staticmethod
	def html_escape(str) :
		html_escape_table = {
		 "&": "&amp;",
		 '"': "&#34;",
		 "'": "&#39;",
		 ">": "&gt;",
		 "<": "&lt;",
		 }
		return "".join(html_escape_table.get(c,c) for c in str)  #escape html entities

 	
	@staticmethod
	def format_post_message(text):

                quote_pattern = re.compile(r'>>(\d{3,12})$')
		quote_replacement = r'<a class="quote_no">&gt;&gt;\1</a>&nbsp;<a href="#p\1">#</a>'

                youtube_pattern = re.compile(r'(https?://)?((?:www|m)\.)?(youtube|youtu|youtube-nocookie)\.(com|be)/(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})')

		text = text.strip()

		lines = []

		for line in text.splitlines():
		        words = line.split()
			for i in range(len(words)):
			    w = words[i]  #this w will be manipulated
                                
                            yt_match = False
                            quote_match = False
                            wbrifyable = False

                            if w.startswith('http') or w.startswith('youtu') :
                                if youtube_pattern.match(w) :
                                    yt_match = True
			    if len(w) > 35 :
                                wbrifyable = True
                            elif w.startswith('>>') :
                                if quote_pattern.match(w) :
				    quote_match = True

                            #actual setting here
                            w_htmlized = False

                            if wbrifyable is True :
                                w = Handler.wbrify_htmlify(w)
                                w_htmlized = True
                                
                            if yt_match is True :
                                if w_htmlized is False :  # just in case the youtube link was short
                                    w = Handler.html_escape(w)
                                    w_htmlized = True
                                w = "<a href={} target='_blank'>{}</a>".format(words[i],w)

                            elif quote_match is True :
                                w = re.sub(quote_pattern, quote_replacement, words[i])
                                w_htmlized = True

                            if w_htmlized is False :  # for all normal words which may contain html entities
                                w = Handler.html_escape(words[i])

                            words[i] = w

			new_line = ' '.join(words)
			if new_line.startswith('&gt;') :
                            new_line = '<span class=\'quote_txt\'>%s</span>' %new_line
			lines.append(new_line)

		return '<br>'.join(lines)


	@staticmethod
	def wbrify(str) :
		return '<wbr>'.join( [ str[0+x:35+x] for x in range(0, len(str), 35) ] )

        @staticmethod
        def wbrify_htmlify(str) :
            return '<wbr>'.join( [ Handler.html_escape( str[0+x:35+x] ) for x in range(0, len(str), 35) ] )
             

	@staticmethod
	def wbrify_line(txt) :
		lines = []
		for line in txt.splitlines():
			words = line.split()
			for i in range(len(words)) :				
				if len(words[i]) > 35 :
					words[i] = Handler.wbrify(words[i])

			lines.append(' '.join(words))
		return ' '.join(lines)

	@staticmethod
	def single_linify(txt) :
		lines = txt.splitlines()
		return ' '.join(lines)

        @staticmethod
        def userId(): 
            strr = app.config['IP_HASH_STR'].format(request.remote_addr)
            sha256 = hashlib.sha256()
            sha256.update(strr)
            return base64.b64encode(sha256.digest())[:10]



		
		




		
