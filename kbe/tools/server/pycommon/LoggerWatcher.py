# -*- coding: utf-8 -*-

import socket, select, io
import sys
import os
import struct
import traceback
import select
import getpass
import time

from . import Define

Logger_onAppActiveTick         = 701
Logger_registerLogWatcher      = 702
Logger_deregisterLogWatcher    = 703
Logger_writeLog                = 704

CONSOLE_LOG_MSGID = 65501 # log 消息

KBELOG_SCRIPT_INFO    = 0x00000040
KBELOG_SCRIPT_ERROR   = 0x00000080
KBELOG_SCRIPT_DEBUG   = 0x00000100
KBELOG_SCRIPT_WARNING = 0x00000200
KBELOG_SCRIPT_NORMAL  = 0x00000400

logName2type = {
	"NORMAL"  : KBELOG_SCRIPT_NORMAL,
	"INFO"    : KBELOG_SCRIPT_INFO,
	"ERROR"   : KBELOG_SCRIPT_ERROR,
	"DEBUG"   : KBELOG_SCRIPT_DEBUG,
	"WARNING" : KBELOG_SCRIPT_WARNING,
}

class LoggerWatcher:
	"""
	日志观察器基类
	"""
	def __init__( self ):
		"""
		"""
		self.socket = None
		self.msgBuffer = b""

	def connect( self, ip, port ):
		"""
		连接到logger
		"""
		self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.socket.setblocking( True )
		#self.socket.settimeout( 1.0 )
		self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
		self.socket.connect( (ip, port) )
		return self.socket

	def close( self ):
		"""
		"""
		if self.socket is not None:
			self.socket.close()
			self.socket = None

	def registerToLogger( self, uid ):
		"""
		向logger注册
		"""
		msg = io.BytesIO()
		msg.write( struct.pack("=H", Logger_registerLogWatcher ) ) # command
		msg.write( struct.pack("=H", struct.calcsize("=iIiiccB" + "i" * Define.COMPONENT_END_TYPE + "BB") ) ) # package len
		msg.write( struct.pack("=i", uid ) )
		msg.write( struct.pack("=I", 0xffffffff) ) # logtypes filter
		msg.write( struct.pack("=iicc", 0, 0, b"\0", b"\0" ) ) # globalOrder, groupOrder, date, keyStr
		msg.write( struct.pack("=B", Define.COMPONENT_END_TYPE ) ) # component type filter count
		msg.write( struct.pack("=" + "i" * Define.COMPONENT_END_TYPE, *list( range( Define.COMPONENT_END_TYPE ) ))) # component type filter
		msg.write( struct.pack("=BB", 0, 1 ) ) # isfind, first
		self.socket.sendall( msg.getvalue() )

	def deregisterFromLogger( self ):
		"""
		从logger取消注册
		"""
		msg = io.BytesIO()
		msg.write( struct.pack("=H", Logger_deregisterLogWatcher ) ) # command
		msg.write( struct.pack("=H", 0) ) # package len
		self.socket.sendall( msg.getvalue() )

	def sendActiveTick( self ):
		"""
		发送心跳包
		"""
		msg = io.BytesIO()
		msg.write( struct.pack("=H", Logger_onAppActiveTick ) ) # command
		msg.write( struct.pack("=iQ", Define.WATCHER_TYPE, 0) ) # componentType, componentID
		self.socket.sendall( msg.getvalue() )

	def sendLog( self, uid, type, logStr ):
		"""
		向logger发送一条日志
		"""
		if type not in logName2type:
			print( "invalid log type '%s'" % type )
			return
			
		if not isinstance(logStr, bytes):
			logStr = logStr.encode( "utf-8" )
		
		if logStr[-1] != b'\n':
			logStr += b'\n'
		
		logSize = len( logStr )
		
		msg = io.BytesIO()
		msg.write( struct.pack("=H", Logger_writeLog ) ) # command
		msg.write( struct.pack("=H", struct.calcsize("=iIiQiiqII") + logSize ) ) # package len
		msg.write( struct.pack("=i", uid ) )
		msg.write( struct.pack("=I", logName2type[type]) ) # logtype
		msg.write( struct.pack("=i", Define.WATCHER_TYPE ) )
		msg.write( struct.pack("=Qii", 0, 0, 0) ) # componentID, globalOrder, groupOrder
		msg.write( struct.pack("=qI", int(time.time()), 0) ) # time, kbetime
		msg.write( struct.pack("=I", logSize) ) # log size
		msg.write( logStr )
		
		#print(struct.calcsize("=iIiQiiqII") + logSize, len(msg.getvalue()))
		self.socket.sendall( msg.getvalue() )

	def parseLog( self, stream ):
		"""
		从数据流中分解日志
		
		@return: array of bytes
		"""
		self.msgBuffer += stream
		buffLen = len( self.msgBuffer )
		pos = 0
		result = []
		while buffLen >= pos + 4:
			cmdID, dataLen = struct.unpack("=HH", self.msgBuffer[pos:pos + 4])
			pos += 4
			if buffLen < pos + dataLen:
				self.msgBuffer = self.msgBuffer[pos - 4:]
				return result
			
			if cmdID != CONSOLE_LOG_MSGID:
				print( "Unknown command.(id = %s)" % cmdID )
				pos += dataLen
				continue
			
			result.append( self.msgBuffer[pos:pos + dataLen] )
			pos += dataLen
		
		return result

	def receiveLog( self, callbackFunc, loop = False ):
		"""
		接收信息
		"""
		rl = [ self.socket.fileno() ]
		while True:
			rlist, wlist, xlist = select.select( rl, [], [], 1.0 )
			if rlist:
				msg = self.socket.recv( 4096 )
				if len( msg ) == 0:
					print( "Receive 0 bytes, over! fileno '%s'" % self.socket.fileno() )
					return
				
				ms = self.parseLog( msg )
				if ms:
					callbackFunc( ms )
				
				continue
			
			if not loop:
				break

			# 不管怎么样，每隔一段时间发送一次心跳，以避免掉线
			self.sendActiveTick()


