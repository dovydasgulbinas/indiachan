#!/usr/bin/env python
# -*- coding: utf-8 -*- 

import os
from PIL import Image
import time
import random

#turn warning to error
Image.warnings.simplefilter('error', Image.DecompressionBombWarning)

class ImageHandler :

	def __init__ (self, img_file) :
		self.img_file = img_file		
		self.img = None
		self.img_thumb = None

		#default values
		self.size = (0, 0)
		self.img_format = 'JPEG'
		self.save_format = 'jpg'

		self.filename = None
		self.save_path = None

	# returns 1 on success, tuple on failure
	def verify_image(self, save_path) :
		filename = self.img_file.filename
		if len(filename) == 0 :
			return 'image error', 400

		self.filename = os.path.splitext(filename)[0].replace(' ', '_')
		
		try : 			
			self.img = Image.open(self.img_file.stream)			
			self.img.verify()
			
			#exceptions can be thrown from here too because verify() doesn't do full load
			self.img_file.seek(0)
			size_tuple = (130,130)
			
			#reopen again because of verify
			self.img = Image.open(self.img_file.stream)
			self.img_thumb = self.img.convert('RGB')
			self.img_thumb.thumbnail(size_tuple, Image.ANTIALIAS )

		except Exception as e :	
			print 'verify_image exception : %s' %e
			return 'image seems to be corrupt', 400

		self.size = self.img.size
		self.img_format = self.img.format
		self.save_path = save_path

		if self.img_format != 'PNG' and self.img_format != 'JPEG' and self.img_format != 'GIF' :
			return 'image type not allowed', 400

		if self.size[0] < 10 or self.size[1] < 10 :
			return 'image dimension too small', 400
		if self.size[0] > 5000 or self.size[1] > 5000 :
			return 'image dimension too large', 400

		#setting variables
		self.savename_utc = str(int(time.time()*1000000))
		self.save_type = self.img_format.lower()
		if self.save_type == 'jpeg' :
			self.save_type = 'jpg'

		#making sure filename doesn't exist already
		savename_original = '%s.%s' %(self.savename_utc, self.save_type)
		if os.path.isfile( os.path.join(self.save_path, savename_original) ) :
			rand = str(random.randint(1,1000000))
			self.savename_utc = '%s_%s' %(self.savename_utc, rand)

		#saving as tmp_ here itself because to know exact file_size it has to be done.
		#it will be moved in save_image() call in next step
		self.img_size = ImageHandler.bytes_2_human_readable( self.save_tmp_image_and_return_img_size() )

		return 1

	def save_tmp_image_and_return_img_size(self) :
		savename_tmp = 'tmp_%s.%s' %(self.savename_utc, self.save_type)
		savepath_tmp = os.path.join(self.save_path, savename_tmp)
		if self.img_format == 'GIF' :
			self.img_file.seek(0)
			self.img_file.save( savepath_tmp )
		else : 
			self.img.save( savepath_tmp, self.img_format )

		return os.stat(savepath_tmp).st_size

	def save_image( self ) :

		#save the thumbnail
		savename_thumb = '%s_s.jpg' %(self.savename_utc)
		self.img_thumb.save( os.path.join(self.save_path, savename_thumb), 'JPEG' )

		#save the original file (image) by renaming tmp_ file		
		savename_original = '%s.%s' %(self.savename_utc, self.save_type)
		savename_tmp = 'tmp_%s' %savename_original
		
		savepath_original = os.path.join(self.save_path, savename_original)
		savepath_tmp = os.path.join(self.save_path, savename_tmp)

		os.rename(savepath_tmp, savepath_original)

		return 1

	@staticmethod
	def bytes_2_human_readable(number_of_bytes):
		if number_of_bytes <= 0:
			raise ValueError("!!! numberOfBytes can't be smaller than 0 !!!")

		step_to_greater_unit = 1024.

		number_of_bytes = float(number_of_bytes)
		unit = 'bytes'

		if (number_of_bytes / step_to_greater_unit) >= 1:
			number_of_bytes /= step_to_greater_unit
			unit = 'KB'

		if (number_of_bytes / step_to_greater_unit) >= 1:
			number_of_bytes /= step_to_greater_unit
			unit = 'MB'

		precision = 1
		number_of_bytes = round(number_of_bytes, precision)

		return '%s%s' %(number_of_bytes, unit)
		


	def __del__(self):
		if self.img_file :
			self.img_file.close()
			
			if self.savename_utc : 
				savename_tmp = 'tmp_%s.%s' %(self.savename_utc, self.save_type)
				savepath_tmp = os.path.join(self.save_path, savename_tmp)

				#delete tmp file if it exists 
				if os.path.isfile(savepath_tmp) :
					os.remove(savepath_tmp)




