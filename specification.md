# DEFINITIONS

In sections of this document I may use the terms MUST, MUST NOT, SHOULD, SHOULD NOT, MAY and OPTIONAL.  The meaning of these terms is as per RFC2119.

# CONTEXT

I have a client application (MbClient) and a server application (MbServer), written in Python, that communicate with each other over amateur radio High Frequency (HF) radio.  They do this with the assistance of another application called JS8Call, which is free open source software.  JS8Call is a station-to-station messaging application that uses the JS8 protocol and radio transmission data mode that is optimised to work in weak signal conditions.  JS8Call does this by encoding the message onto an audio "carrier" using 8-tone frequency-shift keying (8-FSK) and sending to the transceiver in fixed period time slots called frames.  The audio signal is then used by the radio operator's HF Transceiver to modulate an RF carrier using upper sideband modulation (USB).

MbClient uses the JS8Call service interface to transport requests and responses between the client application and the server application.  The service interface is referred to in some places on the web as the JS8Call API.  The topology of the system is:

  MbClient - JS8Call - Client Computer's Audio - HF Transceiver - Air Waves - HF Transceiver - Server Computer's Audio - JS8Call - MbServer

The client and server computers can be Windows, Linux or macOS.  MbClient and MbServer is developed on a Windows platform.

MbClient connects to JS8Call's service interface, and MbServer connects to JS8Call's service interface, using a localhost TCP/IP connections.  The connection from JS8Call to the HF Transceiver is an audio connection, using speaker and mic/line in to provide two-way communications.

During development and testing of the applications, I cross connect the audio of the client and server computer to avoid having to use the HF Transceivers and the air waves.  Even so, JS8Call encodes the data sent by MbClient and MbServer, and transmits it over a narrow bandwidth, which means it's very slow.  The transmission of a single message can take 180 seconds.  This affects my development productivity.

I need a command line Python application that emulates the JS8Call instances, the HF transceivers and the airwaves. We'll call the application JS8Emu.


# SPECIFICATION

## Configuration

Settings for JS8Emu MUST be contained in a config.ini configuration file that includes the following:
```
[general]
fragment_size = 4
frame_time = 0.1

[interface_1]
port = 2442
callsign = "2E0FGO"
frequency = 3578000
offset = 1250
maidenhead = "IO83"

[interface_2]
port = 2443
callsign = "EA7QTH"
frequency = 7078000
offset = 1500
maidenhead = "JN11"

[interface_3]
port = 2444
callsign = "M0PXO"
frequency = 3578000
offset = 1750
maidenhead = "JO02"

[interface_4]
port = 2445
callsign = "M7PJO"
frequency = 7078000
offset = 2000
maidenhead = "IO92"
```

## JS8Emu service interface Instances

A single instance of JS8Emu SHOULD interconnect any number of MbClient and MBServer applications by presenting a JS8Call-compliant service interface via TCP/IP.  Each application will connect to its own JS8Emu service interface instance.  Referring to the config.ini above, we can see that each service interface instance has a TCP/IP port number, an amateur radio callsign, a simulated radio frequency and an audio offset.

## Message Types

The messages between an application and the JS8Call service interface are bytes encoded as UTF8.  Several types of message flow back and forth across the JS8Call service interface, and JS8Emu MUST handle these messages and respond as necessary.

### STATION.GET_CALLSIGN

On receiving this message, JS8Emu MUST respond with a STATION.CALLSIGN message on the same service interface instance.

An example of this message is:

```b'{"type": "STATION.GET_CALLSIGN", "value": "", "params": {"_ID": "1769098601798"}}'\n```

where:

* _ID is the current epoch time in milliseconds multiplied by 1000 to produce an integer.


### STATION.CALLSIGN

Used as described in STATION.GET_CALLSIGN.

An example of this message is:

```b'{'params': {'_ID': 1769098601798}, 'type': 'STATION.CALLSIGN', 'value': '2E0FGO'}\n'```

where:

* _ID matches the _ID of the corresponding STATION.GET_CALLSIGN.
* value is the callsign for this service interface instance as defined in config.ini.


### RIG.GET_FREQ

On receiving this message, JS8Emu MUST respond with a RIG.FREQ message on the same service interface instance.

An example of this message is:

```b'{"type": "RIG.GET_FREQ", "value": "", "params": {"_ID": "1769178020732"}}\n'```

where:

* _ID is the current epoch time in milliseconds multiplied by 1000 to produce an integer.
* value is an empty string.


### RIG.FREQ

Used as described in RIG.GET_FREQ.

An example of this message is:

```b'{"params":{"DIAL":7078000,"FREQ":7079025,"OFFSET":1025,"_ID":1769178020732},"type":"RIG.FREQ","value":""}\n'```

where:

* DIAL is the frequency for this service interface instance.
* OFFSET is the audio frequency offset for this service interface instance.
* FREQ is the sum of DIAL and OFFSET.
* _ID matches the _ID of the corresponding STATION.GET_CALLSIGN.
* value is the callsign for this service interface instance as defined in config.ini.


### RIG.SET_FREQ

On receiving this message, JS8Emu MUST override the frequency defined in config.ini and set a new value for this service interface instance.  JS8Emu MUST then send a STATION.STATUS message.

An example of this message is:

```b'{"type": "RIG.SET_FREQ", "value": "", "params": {"DIAL": 3578000, "_ID": "1769098609802"}}\n'```

where:

* _ID is the current epoch time in milliseconds multiplied by 1000 to produce an integer.
* DIAL is the new frequency for this service interface instance.


### STATION.STATUS

JS8Emu MUST send this message from a service interface instance to its connected application after changing a service interface instance attribute, such as frequency.

An example of this message is:

```b'{"params":{"DIAL":3578000,"FREQ":3579025,"OFFSET":1025,"SELECTED":"","SPEED":1,"_ID":"269799409834"},"type":"STATION.STATUS","value":""}\n'```

where:

* _ID is the current epoch time in milliseconds multiplied by 1000 to produce an integer minus - 1499299200000.
* DIAL is the frequency for this service interface instance.
* OFFSET is the audio frequency offset for this service interface instance.
* FREQ is the sum of DIAL and OFFSET.
* SELECTED is the callsign of a station selected by a JS8Call user through its GUI, but in our case is always an empty string.
* SPEED is the JS8 transmission mode, which we will default to 1.
* value is an empty string.


### TX.SEND_MESSAGE

This is a message from a sending application to its connected service interface instance.  JS8Emu MUST do the following:

1. Split the payload in the value field into frames of a length defined by the fragment_size setting in config.ini.  JS8Emu MUST NOT pad any fragments, such as the last fragment in a sequence.
2. Wait for a period defined by the frame_time setting in config.ini.
3. Send the frame to all other connected applications via their service interface instance where the frequency of the service interface instances matches that of the sending application.  This is intended to mimic real-world JS8Call, where all stations receive all messages transmitted on a frequency.

An example of this message is:

```b'{"type": "TX.SEND_MESSAGE", "value": "_payload_", "params": {"_ID": "1769099798706"}}\n'```

where

* _ID is the current epoch time in milliseconds multiplied by 1000 to produce an integer.
* value is the payload to send to all other applications


### RX.ACTIVITY

A data message from JS8Emu to a connected application MUST be split into a sequence of fragments, the fragment size being set by the fragment_size parameter in config.ini.  The transmission of each frame MUST be proceeded by a wait, the duration of which is given by frame_time in config.ini.

An example of this message and the way it is used in a sequence to transport the string "M0PXO: 2E0FGO  +E65~\\n65 - 2025-12-05 - FIFA WORLD CUP DRAW ANNOUNCED\\n" is as follows:
```
b'{"params":{"DIAL":7078000,"FREQ":7080200,"OFFSET":2200,"SNR":18,"SPEED":1,"TDRIFT":1.2999999523162842,"UTC":1769179137513,"_ID":-1},"type":"RX.ACTIVITY","value":"M0PXO: 2E0FGO  "}\n'

b'{"params":{"DIAL":7078000,"FREQ":7080200,"OFFSET":2200,"SNR":17,"SPEED":1,"TDRIFT":0.5,"UTC":1769179148016,"_ID":-1},"type":"RX.ACTIVITY","value":"+E65~\\n65 "}\n'

b'{"params":{"DIAL":7078000,"FREQ":7080200,"OFFSET":2200,"SNR":17,"SPEED":1,"TDRIFT":1.2999999523162842,"UTC":1769179157234,"_ID":-1},"type":"RX.ACTIVITY","value":"- 2025-12-0"}\n'

b'{"params":{"DIAL":7078000,"FREQ":7080200,"OFFSET":2200,"SNR":17,"SPEED":1,"TDRIFT":1.2999999523162842,"UTC":1769179167725,"_ID":-1},"type":"RX.ACTIVITY","value":"5 - FIFA WORLD "}\n'

b'{"params":{"DIAL":7078000,"FREQ":7080200,"OFFSET":2200,"SNR":18,"SPEED":1,"TDRIFT":1.2999999523162842,"UTC":1769179176815,"_ID":-1},"type":"RX.ACTIVITY","value":"CUP DRAW ANNOUNCED\\n"}\n'
```
where:

* DIAL is the frequency for this service interface instance.
* OFFSET is the audio frequency offset for this service interface instance.
* FREQ is the sum of DIAL and OFFSET.
* SNR is signal-to-noise ratio and JM8Emu should set a random number between -20 and +20.
* _ID MUST be -1.
* value is a fragment of the message originally sent using TX.SEND_MESSAGE by another application instance.
* SPEED is the JS8 transmission mode, which we will default to 1.
* TDRIFT is a time drift in ms.  Neither MbClient nor MbServer use this value and so JS8Emu SHOULD set a random number between -2 and +2.
* UTC is the current epoch time in milliseconds multiplied by 1000 to produce an integer.

The last RX.ACTIVITY fragment ends with the byte sequence " \xe2\x99\xa2 " which delimits the end of a fragmented message.


### RX.DIRECTED

The following shows the RX.DIRECTED message, delimited with a new line character (\n), concatenated with an RX.SPOT message.  This is how these messages are used by JS8Call and so JM8Emu SHOULD do the same.  The RX.Directed message carries the reassembled message transported in the sequence of RX.ACTIVITY values.
```
b'{"params":{"CMD":" ","DIAL":7078000,"EXTRA":"","FREQ":7080200,"FROM":"M0PXO","GRID":"","OFFSET":2200,"SNR":18,"SPEED":1,"TDRIFT":1.2999999523162842,"TEXT":"M0PXO: 2E0FGO  +E65~\\n65 - 2025-12-05 - FIFA WORLD CUP DRAW ANNOUNCED \xe2\x99\xa2 ","TO":"2E0FGO","UTC":1769179137513,"_ID":-1},"type":"RX.DIRECTED","value":"M0PXO: 2E0FGO  +E65~\\n65 - 2025-12-05 - FIFA WORLD CUP DRAW ANNOUNCED \xe2\x99\xa2 "}\n{"params":{"CALL":"M0PXO","DIAL":7078000,"FREQ":7080200,"GRID":" JO01","OFFSET":2200,"SNR":18,"_ID":-1},"type":"RX.SPOT","value":""}\n'
```
In the RX.DIRECTED message, the meaning of the field values are as follows:

* CMD is a single space character.
* DIAL is the frequency for this service interface instance.
* OFFSET is the audio frequency offset for this service interface instance.
* FREQ is the sum of DIAL and OFFSET.
* FROM is the callsign of the callsign of the interface that originally sent using TX.SEND_MESSAGE that resulted in this message.
* TO is the callsign that is the second word in the TEXT field, in this case 2E0FGO.
* EXTRA is an empty string.
* SNR is signal-to-noise ratio and JM8Emu should set a random number between -20 and +20.
* _ID is always -1.
* TEXT is the message originally sent using TX.SEND_MESSAGE by another application instance with five bytes appended with these values " \xe2\x99\xa2 ".
* GRID is an empty string.
* value is the same as TEXT.
* SPEED is the JS8 transmission mode, which we will default to 1.
* TDRIFT is a time drift in ms.  Neither MbClient nor MbServer use this value and so JS8Emu SHOULD set a random number between -2 and +2.
* UTC is the current epoch time in milliseconds multiplied by 1000 to produce an integer.

In the RX.SPOT message, the meaning of the field values are as follows:

* CALL is the callsign of the callsign of the interface that originally sent using TX.SEND_MESSAGE that resulted in this message.
* GRID is the maidenhead locator set by maidenhead in the config.ini file for the interface that has a callsign value the same as the FROM value in the preceding RX.DIRECTED.
* SNR should be the same as the SNR value in the preceding RX.DIRECTED.
* _ID is always -1.
* DIAL is the frequency for this service interface instance.
* OFFSET is the audio frequency offset for this service interface instance.
* FREQ is the sum of DIAL and OFFSET.
* value is an empty string.

Note how the delimiter sequence of " \xe2\x99\xa2 " from RX.ACTIVITY messages is passed through in the RX.DIRECTED message.

### RIG.PTT

This message is sent from JS8Emu to a sending application.  There are two variants of this message which I have labelled below as RIG.PTT ON and RIG.PTT OFF.  RIG.PTT ON MUST be sent to a sending application once the frame_time wait period starts (as described above in TX.SEND_MESSAGE point 2).  The RIG.PTT OFF message MUST be sent to the sending application once a frame has been sent.

RIG.PTT ON - ```b'{"params":{"PTT":true,"UTC":1769179120050,"_ID":-1},"type":"RIG.PTT","value":"on"}\n'```

RIG.PTT OFF - ```b'{"params":{"PTT":false,"UTC":1769179118387,"_ID":-1},"type":"RIG.PTT","value":"off"}\n'```

where:

* UTC is the current epoch time in milliseconds multiplied by 1000 to produce an integer.
* _ID is always -1


# REQUIREMENTS
		
With the above in mind, the application you create:

* MUST emulate the above interactions and be extensible as other interactions may be added later
* MUST allow the connection of any number of applications
* MUST be coded in Python and work with Python 3.13
* SHOULD use Python Standard Library functions and classes
* MUST work on Windows 11


# DELIVERABLE

The deliverable is Python code in a runnable state.  The coding convention should be aligned with PEP 8.  Docstrings should be included following the convention of PEP 257.

Please implement in a package structure like this:
```
js8emu/
│
├─ config.ini
├─ js8emu.bat
├─ js8emu.py          ← thin wrapper / legacy entry
│
└─ js8emu/
   ├─ __init__.py
   ├─ __main__.py     ← python -m js8emu
   ├─ cli.py          ← argument parsing, startup
   ├─ config.py       ← config.ini parsing & validation
   ├─ models.py       ← dataclasses (Conn, Interface, State)
   ├─ protocol.py     ← JS8 message builders & parsers
   ├─ scheduler.py    ← frame timing, PTT sequencing
   ├─ server.py       ← asyncio TCP servers
   └─ util.py         ← time, IDs, helpers
```

The code should be delivered as a downloadable zip file.

