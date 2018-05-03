from flask import Flask, redirect, url_for, session, request, jsonify, Markup, make_response
from flask_socketio import SocketIO, emit, join_room, leave_room, close_room, rooms, disconnect
from flask_oauthlib.client import OAuth
from flask import render_template
from flask_pymongo import PyMongo
from bson import ObjectId
from flask import flash
from threading import Lock

import pprint
import os
import json
import pymongo
import gridfs
import sys

app = Flask(__name__)

app.debug = True #Change this to False for production
 
# You must configure these 3 values from Google APIs console
# https://code.google.com/apis/console

url = 'mongodb://{}:{}@{}:{}/{}'.format(
        os.environ["MONGO_USERNAME"],
        os.environ["MONGO_PASSWORD"],
        os.environ["MONGO_HOST"],
        os.environ["MONGO_PORT"],
        os.environ["MONGO_DBNAME"])
    
client = pymongo.MongoClient(url)
db = client[os.environ["MONGO_DBNAME"]]
collection = db['fs.files'] #put the name of your collection in the quotes
fs = gridfs.GridFS(db)

app.secret_key = os.environ['SECRET_KEY']
oauth = OAuth(app)

google = oauth.remote_app(
    'google',
    consumer_key=os.environ['GOOGLE_CLIENT_ID'],
    consumer_secret=os.environ['GOOGLE_CLIENT_SECRET'],
    request_token_params={
        'scope': 'email'
    },
    base_url='https://www.googleapis.com/oauth2/v1/',
    request_token_url=None,
    access_token_method='POST',
    access_token_url='https://accounts.google.com/o/oauth2/token',
    authorize_url='https://accounts.google.com/o/oauth2/auth',
)

@app.context_processor
def inject_logged_in():
    return {"logged_in":('google_token' in session)}
 
@app.route('/')
def index():
    if 'google_token' in session:
        me = google.get('userinfo')
        session['user_id'] = me.data['id']
        return render_template('home.html', listingTable=showListings(),display=displayListing())
    return render_template('home.html',display=displayListing())
  
@app.route('/login')
def login():
    return google.authorize(callback=url_for('authorized', _external=True))
 
@app.route('/logout')
def logout():
    session.pop('google_token', None)
    return redirect(url_for('index'))
  
@app.route('/uploadimg',methods=['GET','POST'])
def upload_img():
	if request.method == 'POST':
		if 'file' not in request.files or request.form['ltitle'] == '' or request.form['pprice'] == '' or request.form['des'] == '' or request.form['ppemail'] == '':
			flash("You did not fill in all the fields.")
		else:
			string = fs.put(request.files['file'], filename=request.files['file'].filename,Listing={"title":request.form['ltitle'],'price':request.form['pprice'], 'description':request.form['des'],'paypaladdress':request.form['ppemail'],'user_id':session['user_id']})
	return redirect(url_for('index'))
  
@app.route('/deleteListing',methods=['POST'])
def delete():
    #delete posts
    global collection
    collection.delete_one({"_id" : ObjectId(str(request.form['id']))})
    return showListings()
  
def showListings():
	tablestr='<table id="listingT"><tr><td>Title</td><td>Description</td><td>Price</td><td>Paypal</td></tr>'
	table=""
	for doc in collection.find():
		if session['user_id'] == doc['Listing']['user_id']:
			tablestr += '<tr class="listing"><td>'
			tablestr += str(doc['Listing']['title'])
			tablestr += "</td><td>"
			tablestr += str(doc['Listing']['description'])
			tablestr += "</td><td>"
			tablestr += "$"+str(doc['Listing']['price'])
			tablestr += "</td><td>"
			tablestr += str(doc['Listing']['paypaladdress'])
			tablestr += "</td><td>"
			tablestr += '<button class="btn btn-danger" onclick="deletefunction(event)" id="' + str(doc.get('_id')) + '">Delete</button></td></tr>'
	tablestr += "</table>"
	table += Markup(tablestr)
	return table
   
def displayListing():
	listing=''
	for doc in collection.find():
		listing+='<figure class="figure">'
		listing+='<img src="/download/'+ doc['filename'] +'" class="figure-img img-fluid rounded listingimgs" alt="somerounded square">'
		listing+='<figcaption class="figure-caption text-center">' + str(doc['Listing']['title']) + '</figcaption>'
		listing+='<figcaption class="figure-caption text-center">$' + str(doc['Listing']['price']) + '</figcaption>'
		listing+='<button class="btn btn-success" onclick="swiab(event)" id="'+ str(doc.get('_id')) +'" type="button" data-toggle="modal" data-target="#buyingModal">Buy</button>'
		listing+='</figure>'
	return Markup(listing)

@app.route('/swiab', methods=['POST'])
def show_item_info():
	listing=''
	for doc in collection.find():
		if request.form['id'] == str(doc.get('_id')):
			listing+='<figure class="figure">'
			listing+='<img src="/download/'+ doc['filename'] +'" class="figure-img img-fluid rounded listingimgs" alt="somerounded square">'
			listing+='<figcaption class="figure-caption text-center">' + str(doc['Listing']['title']) + '</figcaption>'
			listing+='<figcaption class="figure-caption text-center">' + str(doc['Listing']['description']) + '</figcaption>'
			listing+='<figcaption class="figure-caption text-center">$' + str(doc['Listing']['price']) + '</figcaption>'
			listing+='<form target="paypal" action="https://www.paypal.com/cgi-bin/webscr" method="post"> '
			listing+='<input type="hidden" name="business" value="'+str(doc['Listing']['paypaladdress'])+'">'
			listing+='<input type="hidden" name="cmd" value="_cart"><input type="hidden" name="add" value="1">'
			listing+='<input type="hidden" name="item_name" value="'+str(doc['Listing']['title'])+'">'
			listing+='<input type="hidden" name="amount" value="'+str(doc['Listing']['price'])+'"><input type="hidden" name="currency_code" value="USD">'
			listing+='<button type="submit" class="btn btn-success" onclick=getContinueShoppingURL(this.form)>Checkout</button></form>'
			listing+='</figure>'
	return Markup(listing)
	
@app.route('/download/<file_name>')
def downloadimg(file_name):
	grid_fs_file = fs.find_one({'filename': file_name})
	response = make_response(grid_fs_file.read())
	return response
   
@app.route('/search', methods=['POST']) 
def search_bar():
    try:
        search = {}
        search['key'] = request.form['searchvalue']
        print(collection.find(search))
    except Exception as e:
        print(e)
    return redirect(url_for('index'))
 
@app.route('/login/authorized')
@google.authorized_handler
def authorized(resp):
    if resp is None:
        me = 'Access denied: reason=%s error=%s' + request.args['error_reason'] + request.args['error_description']
    session['google_token'] = (resp['access_token'], '')
    return redirect(url_for('index'))
   
@google.tokengetter
def get_google_oauth_token():
    return session.get('google_token')
 
if __name__ == '__main__':
    app.run()
