#!/usr/bin/env python
# coding: utf-8 -*- 

from flask import Flask



app = Flask(__name__)

app.config.from_pyfile('appconfig.cfg')  # this file should contain UPLOAD_FOLDER, MAX_CONTENT_LENGTH, IP_HASH_STR (and maybe more variables in future) set

#all imports go here
from flask import request, render_template
from handler import Handler


@app.route('/')
def home():		
	return render_template('home.html')

@app.route('/rules_and_faq/')
def rules_and_faq():
	return render_template('rules_and_faq.html')

@app.route('/privacy/')
def privacy():
	return render_template('privacy.html')

@app.route('/contact/')
def contact():
	return render_template('contact.html')

@app.route('/banned/')
def banned():
	handler = Handler()
	return handler.handle_banned()

@app.route('/boards/<name>/')
def catalog(name):
	name = name.lower()
	handler = Handler()	
	return handler.handle_catalog(name)


@app.route('/boards/<name>/thread/<int:thread_id>/')
def post(name, thread_id):
	name = name.lower()
	handler = Handler()
	return handler.handle_post(name, thread_id)


# engine methods
@app.route('/engine/start_thread/', methods=['POST'])
def start_thread():
	handler = Handler()
	return handler.handle_start_thread()

@app.route('/engine/add_post/', methods=['POST'])
def add_post():	
	handler = Handler()
	return handler.handle_add_post()

@app.route('/engine/report_post/', methods=['POST'])
def report_post():
	handler = Handler()
	return handler.handle_report_post()

@app.route('/engine/update_post/', methods=['POST'])
def update_post():
	handler = Handler()
	return handler.handle_update_post()


##################################
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(400)
def bad_req(e):
    return 'bad request', 400

@app.errorhandler(500)
def internal_sv_err(e):
    return 'server error', 500

