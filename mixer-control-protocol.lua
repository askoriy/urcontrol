mixer_protocol = Proto("UR44C_MIXER",  "Steinbergs UR44C Mixer")

local f_midi     = ProtoField.string("mixer.midi",     "MIDI")
local f_rawmidi  = ProtoField.string("mixer.midi",     "RAWMIDI")
local f_miditype = ProtoField.string("mixer.miditype", "MIDI Type")
local f_meter    = ProtoField.string("mixer.meter",    "Meter")
local f_type     = ProtoField.string("mixer.type",     "Type")
local f_channel  = ProtoField.int8("mixer.channel",    "Channel")
local f_param    = ProtoField.string("mixer.param",    "Parameter")
local f_value    = ProtoField.int32("mixer.value",     "Value")

mixer_protocol.fields = {
  f_midi,
  f_rawmidi,
  f_miditype,
  f_meter,
  f_type,
  f_channel,
  f_param,
  f_value,
 }


 function string.fromhex(str)
  return (str:gsub('..', function (cc)
      return string.char(tonumber(cc, 16))
  end))
end

function string.tohex(str)
  return (str:gsub('.', function (c)
      return string.format('%02X', string.byte(c))
  end))
end


function offset(addr)
  local offset = 0
  local i = addr
  while i > 2 do
    offset = offset + 1
    i = i - 3
  end
  return addr + offset + 1
end


function mixer_protocol.dissector(buffer, pinfo, tree)
  length = buffer:len()
  if length == 0 then return end

  pinfo.cols.protocol = mixer_protocol.name
  local subtree = tree:add(mixer_protocol, buffer(), string.format("USB Mixer Control (%d bytes)",buffer:len()))

  -- subtree:add_le(f_body,    buffer())


  local midi = ""
  local miditemp = ""
  for i = 0, buffer():len()-1, 4 do
    if buffer(i,1):int()==4 then
      miditemp = miditemp .. buffer(i+1,3):bytes():tohex()
    elseif buffer(i,1):int()==5 then
      miditemp = miditemp .. buffer(i+1,1):bytes():tohex()
      midi = miditemp
      miditemp = ""
      subtree:add(f_midi,    midi)
    elseif buffer(i,1):int()==6 then
      miditemp = miditemp .. buffer(i+1,2):bytes():tohex()
      midi = miditemp
      miditemp = ""
      subtree:add(f_midi,    midi)
    elseif buffer(i,1):int()==7 then
      miditemp = miditemp .. buffer(i+1,3):bytes():tohex()
      midi = miditemp
      miditemp = ""
      subtree:add(f_midi,    midi)
    elseif buffer(i,1):int()==0 then
      break
    end
  end

  -- for continuous messages
  if midi=="" then
    midi=miditemp
    subtree:add(f_midi,    midi)
  end

  -- subtree:add(f_midi,    midi)
  -- subtree:add(f_rawmidi, string.fromhex(midi))
  local rawmidi = ByteArray.new(midi, "")


  if buffer(offset(0x02), 1):int() == 0x30 then
    subtree:add(f_miditype, "Request")
  end



-- Keepalive
  local b_str = buffer(0x00,0x1A):bytes():tohex()

  --                    | 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1|
  --                    | 0 1 2 3 4 5 6 7 8 9 A B C D E F 0 1 2 3 4 5 6 7 8 9 A B C D E F|
  if string.match(midi, "F043103E14000402F7") then
    subtree:add(f_type, "Keepalive")
    pinfo.cols.info:set(string.format("Keepalive"))
  end



-- Change parameter
  --                    | 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1|
  --                    | 0 1 2 3 4 5 6 7 8 9 A B C D E F 0 1 2 3 4 5 6 7 8 9 A B C D E F|
  if string.match(midi, "F043103E14010100....0000............F7") then
  -- --                 "F043103E14010100pppp0000ccvvvvvvvvvvF7"

    local channel = buffer(offset(0x0C), 1):uint()
    local param = buffer(offset(0x08), 1):uint()*128 + buffer(offset(0x09), 1):uint()
    local v4 = buffer(offset(0x0D), 1):int()
    local v3 = buffer(offset(0x0E), 1):int()
    local v2 = buffer(offset(0x0F), 1):int()
    local v1 = buffer(offset(0x10), 1):int()
    local v0 = buffer(offset(0x11), 1):int()

    local value = v4 * 128^4 + v3 * 128^3 + v2*128^2 + v1*128 + v0
    if value > 0x80000000 then
      value = value - 0xFFFFFFFF - 1
    end

    subtree:add(f_type, "Change parameter")
    subtree:add(f_channel, channel+1)
    subtree:add(f_param, param)
    subtree:add(f_value, value)
    pinfo.cols.info:set(string.format("Mixer Change Parameter (ch: %d), param: %d, value: %d", channel+1, param, value))
  end

-- Request parameter
  --                    | 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1|
  --                    | 0 1 2 3 4 5 6 7 8 9 A B C D E F 0 1 2 3 4 5 6 7 8 9 A B C D E F|
  if string.match(midi, "F043303E1401040200....0000..F7") then
     --                 "F043303E1401040200pppp0000ccF7"

    local channel = buffer(offset(0x0D),1):uint()
    local param = buffer(offset(0x09),1):uint()*128 + buffer(offset(0x0A),1):uint()

    subtree:add(f_type, "Request Parameter Value")
    subtree:add(f_channel, channel+1)
    subtree:add(f_param, param)
    pinfo.cols.info:set(string.format("Request Parameter Value: (ch: %d), param: %d", channel+1, param))
  end

-- Reply parameter
    --                    | 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1|
    --                    | 0 1 2 3 4 5 6 7 8 9 A B C D E F 0 1 2 3 4 5 6 7 8 9 A B C D E F|
    if string.match(midi, "F043103E1401040200....0000............F7") then
       --                  F043103E1401040200pppp0000ccvvvvvvvvvvF7
      local param = buffer(offset(0x09), 1):uint()*128 + buffer(offset(0x0A), 1):uint()
      local channel = buffer(offset(0x0D), 1):uint()

      local v4 = buffer(offset(0x0E), 1):int()
      local v3 = buffer(offset(0x0F), 1):int()
      local v2 = buffer(offset(0x10), 1):int()
      local v1 = buffer(offset(0x11), 1):int()
      local v0 = buffer(offset(0x12), 1):int()
  
      local value = v4 * 128^4 + v3 * 128^3 + v2*128^2 + v1*128 + v0
      if value > 0x80000000 then
        value = value - 0xFFFFFFFF - 1
      end

      subtree:add(f_type, "Reply Parameter Value")
      subtree:add(f_channel, channel+1)
      subtree:add(f_param, param)
      subtree:add(f_value, value)
  
      pinfo.cols.info:set(string.format("Reply Parameter Value: (ch %d): param: %d, value: %d", channel+1, param, value))
    end

-- unknown2
  if string.match(midi, "F043003E2607140101000000000.....") then
                       --    00  ........
    pinfo.cols.info:set(string.format("DUMP DATA TO DEVICE"))
  end



-- unknown3: startup
    if string.match(midi, "F043203E1401010000000003F7") then
      subtree:add(f_type, "Startup configure")
      pinfo.cols.info:set(string.format("Startup configure"))
    end


-- unknown4: request
    --                    | 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1|
    --                    | 0 1 2 3 4 5 6 7 8 9 A B C D E F 0 1 2 3 4 5 6 7 8 9 A B C D E F|
    if string.match(midi, "F043303E1401010001..0000..F7") then
                        -- F043303E1401010001pp0000ccF7
                        -- F043303E140101000138000000F7
                        -- F043303E140101000138000001F7
                        -- F043303E140101000138000002F7
                        -- F043303E140101000138000002F7
                        -- F043303E140101000138000003F7
                        -- F043303E140101000138000004F7
                        -- F043303E140101000138000005F7
                        -- F043303E140101000139000000F7
                        -- F043303E14010100013A000000F7
                        -- F043303E14010100013B000000F7
                        -- F043303E14010100013C000000F7
                        -- F043303E14010100013D000000F7

      local param = buffer(offset(0x09), 1):int()
      local channel = buffer(offset(0x0C), 1):int()
      subtree:add(f_type, "Startup request")
      pinfo.cols.info:set(string.format("Startup request: (ch %d): %d", channel+1, param))
    end


-- unknow startup request2
    if string.match(midi, "F043303E140203327FF7") then
      subtree:add(f_type, "Startup request2")
      pinfo.cols.info:set(string.format("Startup request2 unknown (meters?)"))
    end

-- unknown startup request4
if string.match(midi, "F043303E140003F7") then
  subtree:add(f_type, "Startup request4")
  pinfo.cols.info:set(string.format("Startup request4 unknown"))
end




-- unknown: in-dump
    if string.match(midi, "F043003E264714010100000000...") then
      subtree:add(f_type, "Startup input dump")
      pinfo.cols.info:set(string.format("Startup input dump"))
    end

-- firmware query
    if string.match(midi, "F043303E14007002F7") then
      subtree:add(f_type, "Request Firmware Version")
      pinfo.cols.info:set(string.format("Request Firmware Version"))
    end


-- unknown2: in-dump2
    if string.match(midi, "F043103E1400700200424F4F540000000056312E31300000004D41494E0000000056322E3031000000F7") then
      subtree:add(f_type, "Reply Firmware Version")
      -- Boot: 1.10
      -- Main: 2.01
      pinfo.cols.info:set(string.format("Reply Firmware Version"))
    end

-- unknown2: in-dump2
    if string.match(midi, "F043103E14000300060909090911110002393900023131000411111111F7") then
      subtree:add(f_type, "Reply unknown")
      pinfo.cols.info:set(string.format("Reply unknown"))
    end


-- Meters status
    -- Seems with new firmware additional indicators (Music, Voice, Streamin) are not requested from midi, but "generated" on the fly from Windows
    --                    | 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1|
    --                    | 0 1 2 3 4 5 6 7 8 9 A B C D E F 0 1 2 3 4 5 6 7 8 9 A B C D E F|
                    --    "F043103E14020378
    if string.match(midi, "F043103E140203........") then
      subtree:add(f_type, "Meters")

      local meter_ids = {
        [0] = "Input 1",
        [1] = "Input 2",
        [2] = "Input 3",
        [3] = "Input 4",
        [4] = "Input 5",
        [5] = "Input 6",
        [10] = "Mix1 Master L",
        [11] = "Mix1 Master R",
        [12] = "Mix2 Master L",
        [13] = "Mix2 Master L",

        -- 14-19: 8191

        -- [30] = "unknown1", -- -1270 in windows
        -- [31] = "unknown2", -- -1270 in windows
        -- [32] = "unknown3", -- -1270 in windows

        -- [20] = "unknown1",
        -- [35] = "unknown2",
        -- [41] = "unknown3",
        -- [47] = "unknown4",
      }
      -- index+0*128 + index+1 - current values
      -- index+1*128 + index+2 - peak values

      for i = 0, 47 do
        curr_v0 = buffer(offset(7 + i*4+0), 1):int()
        if curr_v0 > 64 then curr_v0 = curr_v0-128 end
        curr_v1 = buffer(offset(7 + i*4+1), 1):int()
        current_val = curr_v0*128 + curr_v1

        peak_v0 = buffer(offset(7 + i*4+2), 1):int()
        if peak_v0 > 64 then peak_v0 = peak_v0-128 end
        peak_v1 = buffer(offset(7 + i*4+3), 1):int()
        peak_val = peak_v0*128 + peak_v1

        if meter_ids[i] then
          subtree:add(f_meter, string.format("%d (%s): %d (peak: %d)", i, meter_ids[i], current_val, peak_val))
        else
          subtree:add(f_meter, string.format("%d: %d (peak: %d)", i, current_val, peak_val))
        end
      end


      pinfo.cols.info:set(string.format("Meters"))
    end




end

DissectorTable.get("usb.bulk"):add(0xffff, mixer_protocol)





--                              | 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1|
--                              | 0 1 2 3 4 5 6 7 8 9 A B C D E F 0 1 2 3 4 5 6 7 8 9 A B C D E F|
--       if string.match(b_str, "||F04310||3E1400||0402F7")                                     keepalive
--       if string.match(b_str, "||F04310||3E1401||0100pp||pp0000||ccvvvv||vvvvvv||F7")         parameter set
--       if string.match(b_str, "||F04330||3E1401||040200||00vv00||00ccF7")                     magic1 (request)
--       if string.match(b_str, "||F04330||3E1401||040200||013600||0000F7")                     trigger effect (request)
--                                 ^^
--                                 F0 - System Exclusive Message
--                                   ^^
--                                   43 - Manufacturer's ID (Yamaha)
--                                     ^^
--                                     1 -change-or-response
--                                     3 -request
--                                      0-device number
--                                         ^^
--                                         3E - Digital mixer
--                                           14 - (ur44c series???)
--                                             xx - data category
--                                             ^^  ^^^^^^  ^^^^^^  ^^^^^^  ^^^^^^
--                                             data
--                                                                                 ^^
--                                                                                 End of Exclusive
--
--
-- USB MIDI Packet:
-- 04 - 3 bytes + continue
-- 05 - 1 byte
-- 07 - 3 bytes


--               SysEx
--
--     F0 43 00 3E  26 07 14 01  01000000000..... - dump data to device
--     F0 43 00 3E  26 47 14 01  0100000000 - input dump
--
--
--     F0 43 30 3E  14 00 03 F7   - startup request4
--     F0 43 10 3E  14 00 03 00  060909090911110002393900023131000411111111F7 - unknown reply
--     F0 43 10 3E  14 00 04 02  F7   - kepalive
--
--
-- ok  F0 43 30 3E  14 00 70 02  F7 - request firmware version
-- ok  F0 43 10 3E  14 00 70 02  00424F4F540000000056312E31300000004D41494E0000000056322E3031000000F7 - reply firmware version
--
--
-- ok  F0 43 10 3E  14 01 01 00  pppp0000ccvvvvvvvvvvF7 - change parameter
--     F0 43 20 3E  14 01 01 00  00000003F7 - startup configure
--     F0 43 30 3E  14 01 01 00  01pp0000ccF7 - unknown startup request
--
-- ok  F0 43 30 3E  14 01 04 02  00pppp0000ccF7 - request parameter
-- ok  F0 43 10 3E  14 01 04 02  00pppp0000ccvvvvvvvvvvF7 - reply parameter
--
--     F0 43 30 3E  14 02 03 32  7FF7 - startup request2
--     F0 43 10 3E  14 02 03 ..  . metters status
