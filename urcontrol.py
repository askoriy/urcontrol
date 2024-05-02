#!/usr/bin/env python3

import sys
import os
import argparse
import threading
import time


import rtmidi

class UR44C():
    '''
        "F043103E14000402F7" - Keepalive
        "F043103E14010100pppp0000ccvvvvvvvvvvF7" - Change Parameter
        "F043303E1401040200pppp0000ccF7" - Query Parameter
        "F043103E1401040200pppp0000ccvvvvvvvvvvF7 - Reply Parameter
        "F043103E140203........" - Reply Meter Status
    '''


    def __init__(self, midi_in, midi_out):
        self.midi_in = midi_in
        self.midi_in.ignore_types(sysex=False)
        self.midi_in.set_callback(self._midi_callback, self)
        time.sleep(0.1)

        self.midi_out = midi_out
        self.received_params = {}
        self.received_param_event = threading.Event()

    @classmethod
    def _sysex_parser(cls, message):
        #change parameter message
        if len(message)==19 and message[:8]==[0xF0, 0x43, 0x10, 0x3E, 0x14, 0x01, 0x01, 0x00]:
            param = message[8]*128 + message[9]
            channel = message[12]
            v32 = message[13]*(128**4) + message[14]*(128**3) + message[15]*(128**2) + message[16]*128 + message[17]
            value = (v32 & 0x7FFFFFFF) - (v32 & 0x80000000)
            return {
                'type': 'change-parameter',
                'channel': channel,
                'param': param,
                'value': value,
            }
        #query parameter message
        elif len(message)==15 and message[:9]==[0xF0, 0x43, 0x30, 0x3E, 0x14, 0x01, 0x04, 0x02, 0x00]:
            param = message[9]*128 + message[10]
            channel = message[13]
            return {
                'type': 'query-parameter',
                'channel': channel,
                'param': param,
            }
        #reply parameter message
        elif len(message)==20 and message[:9]==[0xF0, 0x43, 0x10, 0x3E, 0x14, 0x01, 0x04, 0x02, 0x00]:
            param = message[9]*128 + message[10]
            channel = message[13]
            v32 = message[14]*(128**4) + message[15]*(128**3) + message[16]*(128**2) + message[17]*128 + message[18]
            value = (v32 & 0x7FFFFFFF) - (v32 & 0x80000000)
            # print('DEBUG, PARSED PARAM', channel, param, value)
            return {
                'type': 'reply-parameter',
                'channel': channel,
                'param': param,
                'value': value,
            }
        #keepalive
        elif message==[0xF0, 0x43, 0x10, 0x3E, 0x14, 0x00, 0x04, 0x02, 0xF7]:
            return {'type': 'keepalive'}

        return {'type': 'unknown'}


    def _midi_callback(self, event, obj=None):
        message, timestamp = event
        res = self._sysex_parser(message)
        if res['type']=='reply-parameter':
            obj.received_params[(res['channel'], res['param'])] = res['value']
            obj.received_param_event.set()


    def MIDISendChangeParameterValue(self, parameter, value, channel=0):
        p0 = (parameter >> 7*0) & 0x7F
        p1 = (parameter >> 7*1) & 0x7F
        v32 = value & 0xFFFFFFFF
        v0 = (v32 >> 7*0) & 0x7F
        v1 = (v32 >> 7*1) & 0x7F
        v2 = (v32 >> 7*2) & 0x7F
        v3 = (v32 >> 7*3) & 0x7F
        v4 = (v32 >> 7*4) & 0x7F
        message = [0xF0, 0x43, 0x10, 0x3E, 0x14, 0x01, 0x01, 0x00, p1, p0, 0x00, 0x00, channel, v4, v3, v2, v1, v0, 0xF7]
        self.midi_out.send_message(message)


    def MIDISendQueryParameterValue(self, parameter, channel=0):
        p0 = (parameter >> 7*0) & 0x7F
        p1 = (parameter >> 7*1) & 0x7F
        message = [0xF0, 0x43, 0x30, 0x3E, 0x14, 0x01, 0x04, 0x02, 0x00, p1, p0, 0x00, 0x00, channel, 0xF7]
        self.midi_out.send_message(message)


    def SendKeepalive(self):
        message = [0xF0, 0x43, 0x10, 0x3E, 0x14, 0x00, 0x04, 0x02, 0xF7]
        self.midi_out.send_message(message)


    def SetParameter(self, parameter, value, channel=0, confirm=True, confirm_timeout=3):
        self.MIDISendChangeParameterValue(parameter, value, channel)
        if confirm:
            self.received_params.pop((channel, parameter), None)
            self.received_param_event.clear()
            self.MIDISendQueryParameterValue(parameter, channel)
            if self.received_param_event.wait(confirm_timeout):
                received_value = self.received_params.pop((channel, parameter), None)
                self.received_param_event.clear()
                if received_value == value:
                    return True
            return False
        else:
            return True

    def GetParameter(self, parameter, channel=0, check_timeout=3):
        self.received_params.pop((channel, parameter), None)
        self.received_param_event.clear()
        self.MIDISendQueryParameterValue(parameter, channel)

        if self.received_param_event.wait(check_timeout):
            received_value = self.received_params.pop((channel, parameter), None)
            self.received_param_event.clear()
            return received_value
        return None

    def SetParameterByName(self, unit, name, value, input=0):
        param_num, min_val, max_val, def_val, val_descr, notes = getattr(unit, name)
        assert min_val <= value <= max_val
        assert 0 <= input <= 5        
        return self.SetParameter(param_num, value, input)

    def GetParameterByName(self, unit, name, input=0):
        param_num, min_val, max_val, def_val, val_descr, notes = getattr(unit, name)
        assert 0 <= input <= 5        
        return self.GetParameter(param_num, input)


    def ResetConfig(self):
        message = bytes.fromhex(initialize_bulk_message)
        # self.midi_out.send_message(message)

        # somehow rtmidi not work with large sysex. Use amidi as workaround
        open('/tmp/reset.syx', 'wb').write(message)
        os.system('amidi --p hw:2,0,1 -s /tmp/reset.syx')




initialize_bulk_message ="""
F043003E2D6F1401010000000001465F4375727265006E745363656E650000000000000000000000005B27000008640500000001000406000701010008000101
0050010100085101010001000148001101010012010001005A0101005B1101010001000200107201010073010144007401010075012201000100060000200101
00010101000002010100030101000004010100310102010032010100331101010034010100083501010036010144003701010009012001000A01010052010101
0053010100080B0101000C010100000D0101005401020100550101000E100101000F000100001000010056000104005700010001002401001301010014000101
005C010100085D0101001501014000160101005E010201005F010100171000010018000100006000010061000144000100060051404001000400524001000100
00010036001053010200540102000055010100560100010057010100580001010059010100005A0102005B010100005C0101005D010002005E0101005F000102
0060010100006101010062010200006301020001000406002A01010036000101002B010100002C0101002D010200002E0102002F010001003001010031000101
00320101000047010100330101400034010200350100010037010100440101010038010100003901020045010104003A0101003B010002003C01010046010101
003D010100003E0102003F0102000001000100400140010041010100420001010043010100004401010045010100004601010047010001004801010049000101
004A010100004B0101004C010100004D0101004E010001006A0101006B110101004F01010000500101006C010104006D01010102012001010301020104000101
0105010100010100020065010100006601010067010001006801010069000101006A010100006B0101006C010100006D0101006E010001006F01010070000101
0071010100007201010073010100007401010075010001007601010077000101007801010000790101007A010100007B0101007C010001007D0101007E000101
007F010100000001010001010144000201010003012201000401010005110101000601010008070101000801014400090101000A012201000B0101000C110101
000D010100080E0101000F010144001001010011012201001201010013110101001401010008150101001601014400170101001801220100190101001A110101
001B010100081C0101001D010144001E0101001F0122010020010100211101010022010100082301010024010144002501010026012201002701010028110101
0029010100082A0101002B010144002C0101002D012201002E010100481101010049010100084A0101004B010244004C0101004D012202004E01010001120001
001C010100001D0101006401010400650101001E012001001F010100660101010067010100082000010021000100006800010069002201000100010025200101
0001000100103E0104003F010444006E0104006F012204004001040041110104007001040008710104015A010440015B0104015C010004015D01040001020002
007601010008770101007801014400790101007A012201007B0101007C110101007D010100087E0001007F000144010000010101000001000100060106200101
010701010100080101000100030801090101010A010001010B01010001020001010C010101000D0101010E01010000010001010F014001011000020111000101
01120002010013010101140101000115010101160100010117010101180001010119010101001A0101011B010100011C0101011D010001011E0101011F000101
0120010101002101010122010100012301010124010001012501010126000101012701010100280101000100020801290101012A010001012B0101012C000101
012D010101002E0102012F0101000130010200010004020131010101320001010133010101003401010135010100013601020137010002013801010139000101
013A01010001010002013B010100013C0101013D010001013E0101013F0001010140010101004101020142010100014301020001000401014401010145000101
014601010100470101014801010001490101014A010001014B0101014C000101014D010101004E0101014F010100015001010151010001015201010153000101
015401010100550101015601010001570101015801000101590101445F0043757272656E74005363656E650000000000000000000000005B270000610E200000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001010101010001000000000000000000
00000000020002020202020000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000101000101
01010101010001010101010101000101010101010100010101010101010067676767676767006767676767676700676767676767670067676700000000000000
00000000000000000000000000000000000000000000000000000001010001016767676700000000003030303100303030313030300031303030313030003031
30303031300031204261736963000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000003031204200617369630000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000003031204261736900630000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003031200042617369630000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000003031204261730069630000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000003031002042
61736963000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
0000000000000000000000000000000000000000000000000000000000000000380025001315003500570048002A390007005F003851002500130035002A5700
480039000755005F00380025000A130035005700485500390007005F00283800250013003555005700480039002A07005F0038002545001300350057002A4800
390007005F54003800250013002A35005700480039550007005F001F00222A00350007005A540053004C007600007E001F002A0035150007005A005300204C00
76007E001F01002A00350007002A5A0053004C007600007E001F002A000A350007005A005350004C0076007E00001F002A0035000755005A0053004C00007600
7E001F002A0500350007005A002853004C0076007E00001E2D3C495649003C58601E2D3C490056493C58601E2D003C4956493C5860001E2D3C4956493C005860
1E2D3C495600493C58601E2D3C004956493C58600100010101010000010002010101010100000001020101010100010000010201010001010100000102000101
01010100000001020101010101000000010264646400645A6464646464006464645A6464640064646464645A640064646464646464005A646464646464006464
5A6464646400646464645A646400646446465E4038004050464046465E004038405046404600465E4038405046004046465E4038400050464046465E40003840
5046404646005E403840504640001E324745443220004B771E324745440032204B771E324700454432204B771E003247454432204B00771E324745443200204B
771E324745004432204B770500024D00040107002B44000A006A007E002A120105004D0004140107002B000A00226A007E0012010551004D0004010700222B00
0A006A007E1500120105004D000A040107002B000A11006A007E0012012805004D0004010751002B000A006A000A7E00120105004D4500040107002B00080A00
6A007E001254010C0C0C0C0C0C000C0C0C0C0C0C0C000C0C0C0C0C0C0C000C0C0C0C0C0C0C000C0C0C0C0C0C0C000C0C0C0C0C0C0C000C0C0C0C0C0C0C000C0C
0C0C0C0C700074717670717374007670747176707100737476707471760070717374767074007176707173747600707471767071730074767074717670007173
7476340017050064002E000401086A00340066001D5401340017006400282E0004016A0034450066001D01340022170064002E000444016A00340066002A1D01
340017006414002E0004016A0022340066001D01345100170064002E002204016A0034006615001D01340017000A64002E0004016A1100340066001D01284835
4743445060006B6F48354743440050606B6F48354700434450606B6F48003547434450606B006F48354743445000606B6F48354743004450606B6F3400025200
0D013B006944001E0020003F002A5200340052000D54013B0069001E002220003F00520034550052000D013B002269001E0020003F15005200340052002A0D01
3B0069001E110020003F0052002A340052000D013B510069001E0020000A3F00520034005255000D013B006900081E0020003F005255000C0E10101310001010
100C0E10100013101010100C0E0010101310101010000C0E10101310100010100C0E10101300101010100C0E100010131010101020001E1C1E1F20241E000B20
1E1C1E1F2000241E0B201E1C1E001F20241E0B201E001C1E1F20241E0B00201E1C1E1F2024001E0B201E1C1E1F0020241E0B34001805005900230075000A7A00
7C00500010550034001800590028230075007A007C55005000100034002A1800590023007545007A007C0050002A100034001800595400230075007A002A7C00
500010003455001800590023002275007A007C005055001000340018002A5900230075007A15007C00500010002A3400340034003455003400340034002A3400
340034003455003400340034002A3400340034003455003400340034002A3400340034003455003400340034002A3400340034003455003400340034002A3400
340034003455003400340034002A3400340034003455003400340034002A34003400340034550034000000000020000000000000000000000000000000006464
646464643801003800380038002A380038001F001F55001F001F001F002A1F001E1E1E1E1E401E01010101010100646464646464460046464646460101000101
01011E1E1E001E1E1E050005000A0500050005000555000C0C0C0C0C0C00000000000000010001010101017070007070707034003405003400340034002A3400
0101010101400148484848484800340034003400345500340034000C0C280C0C0C0C0101010001010120202020002020340034003415003400340034002A3400
3400340034550034003400000028170A0204321D08000C1B7F2001010100016767676700600009084F00000000003232131300003D003D323228281E1E000000
404000000800080202000001010032323232404040004001012E2E0000002F2F464635351C001C00002F2F000000040402020000000000000000004040004040
00006464000000424250501E1E001D1D31312A2A00000001010202000000000000000000400040404003034B4B000000282832325000505A5A28282B2B000000
060602020000000000000000000040404040000014001400000F000F000A7676660066000014000101010167670067670000000000007F7F7F7F7F7F7F7F7F7F
7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F7F017E010101010101010067676767676767006700
0000000000000000000000000000000000000000000000000000000000000000000000000000000000000100000040000040037E000000007F00070101000101
010101010100010101010000000000010117171111006D006D0065653C51003C0000000000200101373728287F01007F00520052002A01011414000001000101
010101000000212131316D006D05003A3A6300630000010000116B02270000136B02270009006B022700245D070044000000000000000DF7
"""



class UR44C_Params_Mixer:
    #                   #   ID    # Range      Def    Values explain      Notes
    InputMix1Solo       = (  7,    0,   1,       0,   "0:unsolo; 1:solo", None)
    InputMix2Solo       = (  8,    0,   1,       0,   "0:unsolo; 1:solo", None)
    InputMix3Solo       = (209,    0,   1,       0,   "0:unsolo; 1:solo", None)
    InputMix1Mute       = (  9,    0,   1,       1,   "0:mute; 1:unmute", None)
    InputMix2Mute       = ( 10,    0,   1,       1,   "0:mute; 1:unmute", None)
    InputMix3Mute       = (211,    0,   1,       1,   "0:mute; 1:unmute", None)
    InputMix1Volume     = ( 12,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    InputMix2Volume     = ( 13,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    InputMix3Volume     = (213,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    InputMix1Pan        = ( 15,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)
    InputMix2Pan        = ( 16,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)
    InputMix3Pan        = (215,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)

    InputStereo         = (  0,    0,   1,       0,   "0:off; 1:input1+input2-stereo",   "ch0, ch2, ch4 only")
    InputHPF            = (  3,    0,   1,       0,   "0:off; 1:on",                     "ch0-ch3 only")
    InputInvertPhase    = (  2,    0,   1,       0,   "0:normal; 1:inverted", None)
    InputFXRec          = (177,    0,   1,       0,   "0:off; 1:on", None)
    InputFX1Enabled     = (178,    0,   1,    None,   "0:off; 1:on",  "Inactive when No Effect, enabled otherwise")
    InputFX1Type        = (182,    0,   6,       0,   "0:No Effect; 1:Ch.Strip; 2:Clean; 3:Crunch; 4:Lead; 5:Drive; 6:Pitch Fix", None)
    InputFX2Enabled     = (179,    0,   1,    None,   "0:off; 1:on",                     "Inactive when No Effect, enabled otherwise")
    InputFX2Type        = (183,    0,   6,       0,   "0:No Effect; 1:Ch.Strip; 2:Clean; 3:Crunch; 4:Lead; 5:Drive; 6:Pitch Fix", None)
    InputFX3Enabled     = (262,    0,   1,    None,   "0:off; 1:on",                     "Inactive when No Effect, enabled otherwise")
    InputFX3Type        = (264,    0,   2,       0,   "0:0:No Effect; 1:Gate; 2:Comp", None)
    InputReverbSend     = ( 14,    0, 127,       0,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)

    DAWMix1Solo         = ( 17,    0,   1,       0,   "0:unsolo; 1:solo", None)
    DAWMix2Solo         = ( 18,    0,   1,       0,   "0:unsolo; 1:solo", None)
    DAWMix3Solo         = (219,    0,   1,       0,   "0:unsolo; 1:solo", None)
    DAWMix1Mute         = ( 19,    0,   1,       1,   "0:mute; 1:unmute", None)
    DAWMix2Mute         = ( 20,    0,   1,       1,   "0:mute; 1:unmute", None)
    DAWMix3Mute         = (221,    0,   1,       1,   "0:mute; 1:unmute", None)
    DAWMix1Volume       = ( 21,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    DAWMix2Volume       = ( 22,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    DAWMix3Volume       = (223,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    DAWMix1Pan          = ( 23,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)
    DAWMix2Pan          = ( 24,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)
    DAWMix3Pan          = (225,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)

    # For music: ch1, for voice: ch2
    MusicMix1Solo       = (242,   0,    1,       0,   "0:unsolo; 1:solo", None)
    MusicMix2Solo       = (243,   0,    1,       0,   "0:unsolo; 1:solo", None)
    MusicMix3Solo       = (245,   0,    1,       0,   "0:unsolo; 1:solo", None)
    MusicMix1Mute       = (246,   0,    1,       1,   "0:mute; 1:unmute", None)
    MusicMix2Mute       = (247,   0,    1,       1,   "0:mute; 1:unmute", None)
    MusicMix3Mute       = (249,   0,    1,       1,   "0:mute; 1:unmute", None)
    MusicMix1Volume     = (250,   0,  127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    MusicMix2Volume     = (251,   0,  127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    MusicMix3Volume     = (253,   0,  127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    MusicMix1Pan        = (254, -16,   16,       0,   "-16:L16; 0:C; 16:R16", None)
    MusicMix2Pan        = (255, -16,   16,       0,   "-16:L16; 0:C; 16:R16", None)
    MusicMix3Pan        = (257, -16,   16,       0,   "-16:L16; 0:C; 16:R16", None)

    # VoiceMix1Solo       =  (-1,    0,   1,       0,   "0:unsolo; 1:solo", None)   #  (TODO: check params)
    # VoiceMix2Solo       =  (-1,    0,   1,       0,   "0:unsolo; 1:solo", None)
    # VoiceMix3Solo       =  (-1,    0,   1,       0,   "0:unsolo; 1:solo", None)
    # VoiceMix1Mute       =  (-1,    0,   1,       1,   "0:mute; 1:unmute", None)
    # VoiceMix2Mute       =  (-1,    0,   1,       1,   "0:mute; 1:unmute", None)
    # VoiceMix3Mute       =  (-1,    0,   1,       1,   "0:mute; 1:unmute", None)
    # VoiceMix1Volume     =  (-1,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    # VoiceMix2Volume     =  (-1,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    # VoiceMix3Volume     =  (-1,    0, 127,     103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    # VoiceMix1Pan        =  (-1,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)
    # VoiceMix2Pan        =  (-1,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)
    # VoiceMix3Pan        =  (-1,  -16,  16,       0,   "-16:L16; 0:C; 16:R16", None)

    ReverbMix1Mute      = ( 77,    0,    1,      1,   "0:mute; 1:unmute", None)
    ReverbMix2Mute      = ( 78,    0,    1,      1,   "0:mute; 1:unmute", None)
    ReverbMix3Mute      = (235,    0,    1,      1,   "0:mute; 1:unmute", None)
    ReverbMix1Volume    = ( 79,    0,  127,    103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    ReverbMix2Volume    = ( 80,    0,  127,    103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    ReverbMix3Volume    = (237,    0,  127,    103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)

    MainMix1Mute        = ( 28,    0,    1,      1,   "0:mute; 1:unmute", None)
    MainMix2Mute        = ( 29,    0,    1,      1,   "0:mute; 1:unmute", None)
    MainMix3Mute        = (229,    0,    1,      1,   "0:mute; 1:unmute", None)
    MainMix1Volume      = ( 30,    0,  127,    103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    MainMix2Volume      = ( 31,    0,  127,    103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    MainMix3Volume      = (231,    0,  127,    103,   "0:-∞; 1:-74dB; 103:0dB; 127:+6dB", None)
    MainMix1Pan         = ( 32,  -16,   16,      0,   "-16:L16; 0:C; 16:R16", None)
    MainMix2Pan         = ( 33,  -16,   16,      0,   "-16:L16; 0:C; 16:R16", None)
    MainMix3Pan         = (233,  -16,   16,      0,   "-16:L16; 0:C; 16:R16", None)

    ReverbType          = ( 65,    0,    3,      0,   "0:Hall; 1:Room; 2:Plate; 3:Delay", None)
    ReverbTime          = ( 66,    0,   69,     23,   "0:0.289; 69:29.0; 23:2.51; 40:4.15", None)  #  (TODO: other types)

    ReverbOutput        = ( 37,    0,    4,      0,   "0:mix1; 1:mix2: 4:mix3", None)
    Headphones2Input    = ( 34,    0,    4,      0,   "0:mix1; 1:mix2: 4:mix3",              "Doesn’t reset when select Initial Data")

    MainMix3FXEnabled   = (268,    0,     1,  None,   "0:off; 1:on",                         "Inactive when No Effect, enabled otherwise")
    MainMix3FXType      = (270,    0,     1,     0,   "0:No Effect; 1:M.B.Comp", None)

    HPFSetting          = (  4,    0,     4,     2,   "0:40Hz; 1:60Hz; 2:80Hz; 3:100Hz; 4:120Hz", None)
    LineInputLevel      = ( 41,    0,     1,     1,   "0:+4dB;1:-10dB",                      "set on ch3")

    PCFX3Enabled        = (265,    0,     1,  None,   "0:off; 1:on",                         "Inactive when No Effect, enabled otherwise")
    PCFX3Type           = (267,    0,     1,     0,   "0:No Effect; 1:Ducker",               "ch1:DAW, ch2:Music, ch3:Voice")
    

class UR44C_Params_ChStrip:
    Enabled             = (178,    0,     1,     1,   "0:off; 1:on", None)
    CompEnabled         = ( 43,    0,     1,     0,   "0:on; 1:off", None)
    CompDrive           = ( 44,    0,   200,   100,   "0:0.00; 100:5.00; 200:10.00", None)
    CompAttack          = ( 45,   57,   283,   184,   "57:0.092ms; 184:4.122ms; 283:80.00ms", None)
    CompRelease         = ( 46,   24,   300,   159,   "24:9.3ms; 159:92.0ms; 300:999.0ms", None)
    CompRatio           = ( 47,    0,   120,    30,   "0:1.00; 30:2.50; 60:4.0.0; 90:14.0; 120:inf", None)
    CompKnee            = ( 48,    0,     2,     1,   "0:soft; 1:medium; 2:hard", None)
    CompSideChEnabled   = (199,    0,     1,     1,   "0:off; 1:on", None)
    CompSideChFreq      = ( 51,    4,   124,    30,   "4:20Hz; 30:90.0Hz; 124:20kHz", None)
    CompSideChGain      = ( 52,    0,   360,   133,   "0:-18.0dB; 133:-4.7dB; 360:18dB", None)
    CompSideChQ         = ( 53,    0,    60,    12,   "0:0.50; 12:1.00; 60:16", None)
    Morphing            = ( 54,    0,   200,   100,   "0:0:00; 100:5:00; 200:10:00", None)
    EQEnabled           = ( 55,    0,     1,     0,   "0:on; 1:off", None)
    EQHighEnabled       = (196,    0,     1,     1,   "0:off; 1:on", None)
    EQHighFreq          = ( 56,   60,   124,   112,   "60:500Hz; 112:10.0kHz; 124:20.0kHz", None)
    EQHighGain          = ( 57,    0,   360,   180,   "0:-18dB; 180:0.0dB; 360:18dB", None)
    EQMidEnabled        = (197,    0,     1,     1,   "0:off; 1:on", None)
    EQMidFreq           = ( 58,    4,   124,    71,   "4:20Hz; 71:1.00kHz; 124:20kHz", None)
    EQMidGain           = ( 59,    0,   360,   180,   "0:-18dB; 180:0.0dB; 360:18dB", None)
    EQMidQ              = ( 60,    0,    60,    12,   "0:0.50; 12:1.00; 60:16", None)
    EQLowEnabled        = (198,    0,     1,     1,   "0:off; 1:on", None)
    EQLowFreq           = ( 61,    4,    72,    32,   "4:20Hz; 100.0Hz; 72:1kHz", None)
    EQLowGain           = ( 62,    0,   360,   180,   "0:-18dB; 180:0.0dB; 360:18dB", None)
    OutputLevel         = ( 63,    0,   360,   180,   "0:-18dB; 180:0.0dB; 360:18dB", None)


class UR44C_Params_Clean:
    Volume              = (104,    0,   100,    19,    "0   1.9  10", None)
    Distortion          = (105,    0,   100,     0,    "off  10", None)
    Blend               = (103,    0,   100,    50,    "0  5.0  10", None)
    Modulation          = (200,    0,     2,     1,    "0:Chorus; 1:off; 2:Vibrato", None)
    Bass                = (106,    0,   100,    61,    "0  6.1  10", None)
    Middle              = (107,    0,   100,    50,    "0  5.0  10", None)
    Treble              = (108,    0,   100,    40,    "0  4.0  10", None)
    Presence            = (109,    0,   100,    30,    "0  3.0  10", None)
    VibrationSpeed      = (117,    0,   100,    50,    "0  5.0  10", None)
    VibrationDepth      = (118,    0,   100,    50,    "0  5.0  10", None)
    GateEnabled         = (200,    0,     1,     0,    "0:off; 1:on", None)
    GateLevel           = (201,    0,   100,    20,    "0  2.0  10", None)
    SpeakerType         = (113,    1,     8,     8,    "1:BS 4x12; 2:AC 2x12; 3:AC 1x12; 4:4x10; 5:BC 2x12; 6:AM 4x12; 7:YC 4x12; 8:JC 2x12", None)
    MicPosition         = (115,    0,     1,     0,    "0:Center; 1:Edge", None)
    Output              = (111,    0,   127,    64,    "-11.9dB", None)


class UR44C_Params_Crunch:
    AmpType             = (121,    0,     1,     1,    "0:Normal; 1:Bright", None)
    Gain                = (122,    0,   100,    46,    "4.6", None)
    Bass                = (124,    0,   100,    47,    "0-10", None)
    Middle              = (125,    0,   100,    70,    "0-10", None)
    Trebble             = (126,    0,   100,    53,    "0-10", None)
    Presence            = (127,    0,   100,    28,    "0-10", None)
    GateEnabled         = (200,    0,     1,     0,    "0:off; 1:on", None)
    GateLevel           = (201,    0,   100,    20,    "0  2.0  10", None)
    SpeakerType         = (113,    1,     8,     4,    "1:BS 4x12; 2:AC 2x12; 3:AC 1x12; 4:4x10; 5:BC 2x12; 6:AM 4x12; 7:YC 4x12; 8:JC 2x12", None)
    MicPosition         = (115,    0,     1,     0,    "0:Center; 1:Edge", None)
    Output              = (111,    0,   127,    64,    "-11.9dB", None)


class UR44C_Params_Lead:
    AmpType             = (139,    0,     1,     0,    "0:High; 1:Low", None)
    Gain                = (140,    0,   100,   100,    "0-10", None)
    Master              = (146,    0,   100,    49,    "0-10", None)
    Bass                = (142,    0,   100,    66,    "0-10", None)
    Middle              = (143,    0,   100,    80,    "0-10", None)
    Treble              = (144,    0,   100,    30,    "0-10", None)
    Presence            = (145,    0,   100,    29,    "0-10", None)
    GateEnabled         = (200,    0,     1,     0,    "0:off; 1:on", None)
    GateLevel           = (201,    0,   100,    20,    "0  2.0  10", None)
    SpeakerType         = (113,    1,     8,     4,    "1:BS 4x12; 2:AC 2x12; 3:AC 1x12; 4:4x10; 5:BC 2x12; 6:AM 4x12; 7:YC 4x12; 8:JC 2x12", None)
    MicPosition         = (115,    0,     1,     0,    "0:Center; 1:Edge", None)
    Output              = (111,    0,   127,    42,    "-11.9dB", None)


class UR44C_Params_Drive:
    AmpType             = (157,    0,     5,     4,    "0:Raw1; 1:Raw2; 2:Vintage1; 3:Vintage2; 4:Modern1; 5:Modern2", None)
    Gain                = (158,    0,   100,    75,    "0-10", None)
    Master              = (164,    0,   100,    40,    "0-10", None)
    Bass                = (160,    0,   100,    40,    "0-10", None)
    Middle              = (161,    0,   100,    50,    "0-10", None)
    Treble              = (162,    0,   100,    80,    "0-10", None)
    Presence            = (163,    0,   100,    90,    "0-10", None)
    GateEnabled         = (200,    0,     1,     0,    "0:off; 1:on", None)
    GateLevel           = (201,    0,   100,    20,    "0  2.0  10", None)
    SpeakerType         = (113,    1,     8,     6,    "1:BS 4x12; 2:AC 2x12; 3:AC 1x12; 4:4x10; 5:BC 2x12; 6:AM 4x12; 7:YC 4x12; 8:JC 2x12", None)
    MicPosition         = (115,    0,     1,     0,    "0:Center; 1:Edge", None)
    Output              = (111,    0,   127,    42,    "-11.9dB", None)


class UR44C_Params_PitchFix:
    Pitch               = (272,-1200,  1200,     0,    "", None)
    Formant             = (273,    2,   126,    64,    "64: 0; 2: -52; 126: 62", None)
    Mix                 = (277,    0,   126,   126,    "", None)
    Key                 = (282,    0,    11,     0,    "0:C; 11:B", None)
    Scale               = (283,    0,     7,     0,    "0:Custom; 1:Single; 2:Major; 3:Natural Minor; 4:Harmonic Minor; 5: Melodic Minor; 6:Pentatonic; 7:Chromatic", None)
    NoteC               = (285,    0,     1,     1,    "", None)
    NoteCsharp          = (286,    0,     1,     1,    "", None)
    NoteD               = (287,    0,     1,     1,    "", None)
    NoteDsharp          = (288,    0,     1,     1,    "", None)
    NoteE               = (289,    0,     1,     1,    "", None)
    NoteF               = (290,    0,     1,     1,    "", None)
    NoteFsharp          = (291,    0,     1,     1,    "", None)
    NoteG               = (292,    0,     1,     1,    "", None)
    NoteGsharp          = (293,    0,     1,     1,    "", None)
    NoteA               = (294,    0,     1,     1,    "", None)
    NoteAsharp          = (295,    0,     1,     1,    "", None)
    NoteB               = (296,    0,     1,     1,    "", None)
    NoteLowLimit        = (280,    0,   127,     0,    "0:C2; 127:G8", None)
    NoteHighLimit       = (281,    0,   127,   127,    "0:C2; 127:G8", None)
    MidiControl         = (278,    0,     1,     0,    "", None)
    MidiRealTimeControl = (279,    0,     1,     0,    "", None)
    # Midi control: Off: 278=0      Settings: 279=0    RealTime: 278=1,279=1


class UR44C_Params_Hall:
    ReverbTime          = ( 66,    0,    69,    23,    "0:0.103ms; 23:2.51s; 69:31.0s", None)
    InitialDelay        = ( 68,    0,   127,     2,    "0:0.1ms; 2:3.2ms; 127:200.0ms", None)
    Decay               = ( 74,    0,    63,    27,    "", None)
    RoomSize            = ( 71,    0,    31,    29,    "", None)
    Diffusion           = ( 67,    0,    10,    10,    "", None)
    HPF                 = ( 69,    0,    52,     4,    "0:20Hz; 4:32Hz; 52:8.0kHz", None)
    LPF                 = ( 70,   34,    60,    50,    "34:1kHz; 50:6.3kHz; 60:20kHz", None)
    HiRatio             = ( 72,    1,    10,     8,    "1:0.1; 8:0.8; 10:1.0", None)
    LowRatio            = ( 73,    1,    14,    12,    "1:0.1; 12:1.2; 14:1.4", None)
    LowFreq             = ( 76,    1,    59,    32,    "1:22Hz; 32:800Hz; 59:18kHz", None)


class UR44C_Params_Room:
    ReverbTime          = ( 66,    0,    69,     6,    "0:0.206s; 6:0.780s; 69:26.0s", None)
    InitialDelay        = ( 68,    0,   127,     2,    "0:0.1ms; 2:3.2ms; 127:200.0ms", None)
    Decay               = ( 74,    0,    63,    15,    "", None)
    RoomSize            = ( 71,    0,    31,    15,    "", None)
    Diffusion           = ( 67,    0,    10,     8,    "", None)
    HPF                 = ( 69,    0,    52,     6,    "0:20Hz; 6:40Hz; 52:8.0kHz", None)
    LPF                 = ( 70,   34,    60,    47,    "34:1kHz; 47:4.5kHz; 60:20kHz", None)
    HiRatio             = ( 72,    1,    10,     8,    "1:0.1; 8:0.8; 10:1.0", None)
    LowRatio            = ( 73,    1,    14,    12,    "1:0.1; 12:1.2; 14:1.4", None)
    LowFreq             = ( 76,    1,    59,    32,    "1:22Hz; 32:800Hz; 59:18kHz", None)


class UR44C_Params_Plate:
    ReverbTime          = ( 66,    0,    69,    21,    "0:0.333ms; 21:2.66s; 69:33.3s", None)
    InitialDelay        = ( 68,    0,   127,     2,    "0:0.1ms; 2:3.2ms; 127:200.0ms", None)
    Decay               = ( 74,    0,    63,     5,    "", None)
    RoomSize            = ( 71,    0,    31,    18,    "", None)
    Diffusion           = ( 67,    0,    10,     8,    "", None)
    HPF                 = ( 69,    0,    52,    12,    "0:20Hz; 12:80Hz; 52:8.0kHz", None)
    LPF                 = ( 70,   34,    60,    52,    "34:1kHz; 52:8.0kHz; 60:20kHz", None)
    HiRatio             = ( 72,    1,    10,     9,    "1:0.1; 8:0.9; 10:1.0", None)
    LowRatio            = ( 73,    1,    14,    10,    "1:0.1; 10:1.0; 14:1.4", None)
    LowFreq             = ( 76,    1,    59,    32,    "1:22Hz; 32:800Hz; 59:18kHz", None)


class UR44C_Params_Delay:
    Stereo              = (258,    0,     1,     0,   "0:mono; 1:stereo", None)
    DelayTime           = (259,    1, 13000,  2400,   "1:0.1ms; 240.0ms; 13000:1300.0ms", None)
    Feedback            = (261,   64,   127,    80,   "64:0; 80:15; 127:63", None)
    HighRatio           = (260,    1,    10,     8,   "1:0.1; 8:0.8; 10:1.0", None)


class UR44C_Params_Ducker:
    Input1Source        = (316,    0,     1,     1,    "0:off; 1:on", None)     
    Input2Source        = (317,    0,     1,     1,    "0:off; 1:on", None)     
    VoiceSource         = (318,    0,     1,     0,    "0:off; 1:on", None)     
    Threshold           = (319,   13,    73,    33,    "13:-60dB; 33:-40dB; 73:0dB", None)     
    Range               = (320,    3,    73,    50,    "3:-70dB; 50:-24dB; 72:0dB", None)     
    Attack              = (321,   57,   283,   237,    "57:0.092ms; 237:20.17ms; 283:80.00ms", None)     
    Decay               = (323,    0,   121,    99,    "0:1.3ms; 99:1.0s; 121:5.0s", None)     


class UR44C_Params_MBComp:
    LowGain             = (330,    0,    55,    39,    "0:-∞; 1:-60dB; 39:2dB; 55:18dB", None)
    MidGain             = (335,    0,    55,    39,    "0:-∞; 1:-60dB; 39:2dB; 55:18dB", None)
    HighGain            = (340,    0,    55,    39,    "0:-∞; 1:-60dB; 39:2dB; 55:18dB", None)
    LMxover             = (342,    5,    96,    36,    "5:21.2Hz; 36:125Hz; 96:4.00kHz", None)
    MHxover             = (343,   17,   108,    93,    "17:42.5Hz; 93:3.35kHz; 108:8.00kHz", None)




def open_midi_ports(args):
    midi_in = rtmidi.MidiIn()
    if args.midi_in:
        try:
            index = midi_in.get_ports().index(args.midi_in)
        except ValueError:
            print(f'Cannot find input midi port {args.midi_in}')
            sys.exit(1)
    else:
        index = -1
        for i, v in enumerate(midi_in.get_ports()):
            if 'Steinberg UR' in v:
                index = i
        if index == -1:
            print(f'Cannot find Steinberg UR device')
            sys.exit(1)
    midi_in.open_port(index)
    midi_in.ignore_types(sysex=False)

    midi_out = rtmidi.MidiOut()
    if args.midi_out:
        try:
            index = midi_out.get_ports().index(args.midi_out)
        except ValueError:
            print(f'Cannot find input midi port {args.midi_out}')
            sys.exit(1)
    else:
        index = -1
        for i, v in enumerate(midi_out.get_ports()):
            if 'Steinberg UR' in v:
                index = i
        if index == -1:
            print(f'Cannot find Steinberg UR device')
            sys.exit(1)
    midi_out.open_port(index)

    return midi_in, midi_out



def main():
    formatter = lambda prog: argparse.HelpFormatter(prog,max_help_position=45)
    parser = argparse.ArgumentParser(description='Command line tool to control UR44C by MIDI', formatter_class=formatter)
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose')
    parser.add_argument('--midi-in', '-mi', action='store', help='Input MIDI port', metavar='PORT', default='')
    parser.add_argument('--midi-out', '-mo', action='store', help='Output MIDI port', metavar='PORT', default='')
    parser.add_argument('--input', '-i', action='store', type=int, metavar='input', help='Input number (for Inputs, default:1)', default=1)
    parser.add_argument('--unit', '-u', action='store', metavar='UNIT', help='Unit name (default:mixer)', default='mixer')

    commands = parser.add_argument_group('Commands')
    command = commands.add_mutually_exclusive_group(required=True)
    command.add_argument('--get-midi-ports', '-m', action='store_true', help='Show MIDI ports in system')
    command.add_argument('--list-units', '-lu', action='store_true', help='List unit names')
    command.add_argument('--list-parameters', '-l', action='store_true', help='List available parameters in unit')
    command.add_argument('--get-parameter', '-g', action='store', metavar='PARAMETER', help='Get parameter value')
    command.add_argument('--set-parameter', '-s', action='store', metavar=('PARAMETER', '(VALUE|min|max|def)'), nargs=2, help='Set parameter value')
    command.add_argument('--reset', action='store_true', help='Reset mixer config')

    command.add_argument('--test', action='store_true', help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.unit=='mixer':
        unit = UR44C_Params_Mixer
    elif args.unit=='chstrip':
        unit = UR44C_Params_ChStrip
    elif args.unit=='clean':
        unit = UR44C_Params_Clean
    elif args.unit=='crunch':
        unit = UR44C_Params_Crunch
    elif args.unit=='lead':
        unit = UR44C_Params_Lead
    elif args.unit=='drive':
        unit = UR44C_Params_Drive
    elif args.unit=='pitchfix':
        unit = UR44C_Params_PitchFix
    elif args.unit=='hall':
        unit = UR44C_Params_Hall
    elif args.unit=='room':
        unit = UR44C_Params_Room
    elif args.unit=='plate':
        unit = UR44C_Params_Plate
    elif args.unit=='delay':
        unit = UR44C_Params_Delay
    elif args.unit=='ducker':
        unit = UR44C_Params_Ducker
    elif args.unit=='mbcomp':
        unit = UR44C_Params_MBComp
    else:
        raise Exception('Unit does not exists')

    if args.get_midi_ports:
        print('Input:')
        for port in rtmidi.MidiIn().get_ports():
            print(f'  {port}')
        print('Output:')
        for port in rtmidi.MidiOut().get_ports():
            print(f'  {port}')
    elif args.list_units:
        print('mixer')
        print('chstrip')
        print('clean')
        print('crunch')
        print('lead')
        print('drive')
        print('pitchfix')
        print('hall')
        print('room')
        print('plate')
        print('delay')
        print('ducker')
        print('mbcomp')
    elif args.list_parameters:
        if args.verbose:
            print('NAME                 MIN.VAL MAX.VAL DEF.VAL   VALUE EXPLAIN                      NOTES')
        for i in vars(unit):
            if not i.startswith('__'):
                if args.verbose:
                    attr = getattr(unit, i)
                    print(f'{i:<20} {attr[1]:>7} {attr[2]:>7} {attr[3] if attr[3] is not None else "":>7}   {attr[4]:<35}{attr[5] if attr[5] else ""}')
                else:
                    print(i)


    elif args.get_parameter:
        midi_in, midi_out = open_midi_ports(args)
        ur44c = UR44C(midi_in, midi_out)
        value = ur44c.GetParameterByName(unit, args.get_parameter, args.input-1)
        if args.verbose:
            attr = getattr(unit, args.get_parameter)
            print(f'{args.get_parameter}  |  {attr[4]}')
            print()
            print(f'CURRENT VALUE: {value}')
            print(f'Minimal: {attr[1]}')
            print(f'Maximum: {attr[2]}')
            print(f'Default: {attr[3]}')
            if attr[5]:
                print(f'Notes: {attr[5]}')
        else:
            print(value)

    elif args.set_parameter:
        midi_in, midi_out = open_midi_ports(args)
        ur44c = UR44C(midi_in, midi_out)
        if args.set_parameter[1]=='min':
            value = getattr(unit, args.set_parameter[0])[1]
        elif args.set_parameter[1]=='max':
            value = getattr(unit, args.set_parameter[0])[2]
        elif args.set_parameter[1]=='def':
            value = getattr(unit, args.set_parameter[0])[3]
        else:
            value = int(args.set_parameter[1])
        result = ur44c.SetParameterByName(unit, args.set_parameter[0], value, args.input-1)    
        if not result:
            print('FAILED')
            sys.exit(1)

    elif args.reset:
        midi_in = rtmidi.MidiIn().open_port(0)
        midi_out = rtmidi.MidiOut().open_port(0)
        ur44c = UR44C(midi_in, midi_out)
        ur44c.ResetConfig()

    elif args.test:
        midi_in, midi_out = open_midi_ports(args)
        ur44c = UR44C(midi_in, midi_out)
        for i in range(8):
            ur44c.SetParameterByName(UR44C_Params_Mixer, 'MainMix1Volume', 30, 0)
            time.sleep(0.2)

            ur44c.SetParameterByName(UR44C_Params_Mixer, 'MainMix1Volume', 103, 0)
            time.sleep(0.2)


if __name__=='__main__':
    main()
