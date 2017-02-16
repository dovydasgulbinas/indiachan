#!/usr/bin/env python
# coding: utf-8 -*- 

import psycopg2

con = psycopg2.connect("dbname='indiach_db' user='indiach_role'")

def process_line(line) :
	split = line.split(',')
	
	board = split[0].strip()
	display_name = split[1].strip()
	level = int(split[2].strip())

	cur = con.cursor()

	db_str = 'INSERT INTO boards (board, parent_board, level, display_name) ' \
	'VALUES (%s, %s, %s, %s)'

	cur.execute(db_str, (board,board,level,display_name) )




if __name__ == '__main__' :
	with open('board_list.txt') as f:
		for line in f:
			line = line.strip()
			if len(line) > 5 and line.startswith('#') == False :
				process_line(line)

		con.commit()
		con.close()