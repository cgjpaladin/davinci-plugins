# 逆向 DaVinci Resolve Fairlight 预设 .dat 文件 — 完整版

## 背景
我是后期总监，DaVinci Resolve Studio 20.3.2。Fairlight 混音页配置了音频总线预设，保存为 Console Flexi 文件：
`~/Library/Preferences/Blackmagic Design/DaVinci Resolve/Fairlight/Presets/CONSOLE_FLEXI/交付总线设置.dat`
420KB 大小，BMD 私有二进制格式。拖不进豆包，所以把 hex dump 直接放在下面。

## 目标
用 Python 解析此文件，提取所有设置项（不止当前设置，而是格式里所有可能的字段）。需要你：
1. 推断文件结构（分段、字段类型、编码方式）
2. 给出 Python 解析脚本框架
3. 标注不确定区域，说明需要更多样本验证的地方
4. 判断能否从 BMD SDK 获取格式文档

## 已知信息
- `66886677` 反复出现，可能是 type tag/magic number
- 文件头 `0006 6943 6688 6677 0100 0000 3769 0600` — 末4字节 LE = 420151 ≈ 420167(文件大小)
- 数据混合：4字节 LE 整数 + null-terminated UTF-8 + float32 + 大段参数块
- 总线：Dialogue, Music, SFX, Ambience + Master Bus
- FX: Clean, De-ess, Levelling, EQ, Dynamics, Duck, Instrumental, Maximize, Spread
- BMD 插件 ID: De-Esser:1112360051, Multiband Compressor:1112360043, Stereo Width:1112360051
- 轨道名: VO 1-2, OS 3, SFX 4-7, BGM 8-10

## 文件 hex dump（前 4096 字节）

00000000: 0006 6943 6688 6677 0100 0000 3769 0600  ..iCf.fw....7i..
00000010: 1256 7498 0100 0000 4164 7244 6174 6162  .Vt.....AdrDatab
00000020: 6173 6500 0000 0000 0000 0000 0000 0000  ase.............
00000030: 0000 0000 0000 0000 0500 0000 6688 6677  ............f.fw
00000040: 0100 0000 2400 0000 0500 0000 0167 1256  ....$........g.V
00000050: 0500 0000 0000 0000 0167 1256 0500 0000  .........g.V....
00000060: 0000 0000 0167 1256 0500 0000 4175 746f  .....g.V....Auto
00000070: 4d69 7800 0000 0000 0000 0000 0000 0000  Mix.............
00000080: 0000 0000 0000 0000 0000 0000 0100 0000  ................
00000090: 6688 6677 0100 0000 8f07 0000 0100 0000  f.fw............
000000a0: 5d03 0000 0b00 0000 4175 746f 4d69 784d  ].......AutoMixM
000000b0: 6169 6e66 8866 7701 0000 0051 0300 0002  ainf.fw....Q....
000000c0: 0000 0007 0000 0044 6566 6175 6c74 0400  .......Default..
000000d0: 0000 4e6f 6e65 0100 0000 0f00 0000 4175  ..None........Au
000000e0: 746f 4d69 7843 6c61 7373 6966 7901 0000  toMixClassify...
000000f0: 0013 0000 0041 7574 6f4d 6978 536f 7274  .....AutoMixSort
00000100: 416e 644c 6162 656c 0100 0000 0800 0000  AndLabel........
00000110: 4469 616c 6f67 7565 0100 0000 1000 0000  Dialogue........
00000120: 5365 7061 7261 7465 5370 6561 6b65 7273  SeparateSpeakers
00000130: 0b00 0000 1200 0000 4175 746f 4d69 784e  ........AutoMixN
00000140: 6f72 6d61 6c69 7a65 3a31 0100 0000 1800  ormalize:1......
00000150: 0000 5472 6163 6b46 7853 6574 7469 6e67  ..TrackFxSetting
00000160: 3a43 6c65 616e 3a31 3a30 0100 0000 1700  :Clean:1:0......
00000170: 0000 4d61 6372 6f46 7853 6574 7469 6e67  ..MacroFxSetting
00000180: 3a44 652d 6573 733a 3101 0000 001c 0000  :De-ess:1.......
00000190: 0054 7261 636b 4678 5365 7474 696e 673a  .TrackFxSetting:
000001a0: 4c65 7665 6c6c 696e 673a 313a 3101 0000  Levelling:1:1...
000001b0: 0015 0000 0054 7261 636b 4678 5365 7474  .....TrackFxSett
000001c0: 696e 673a 4551 3a31 3a33 0100 0000 1b00  ing:EQ:1:3......
000001d0: 0000 5472 6163 6b46 7853 6574 7469 6e67  ..TrackFxSetting
000001e0: 3a44 796e 616d 6963 733a 313a 3401 0000  :Dynamics:1:4...
000001f0: 0014 0000 004d 6978 4c65 7665 6c3a 4d69  .....MixLevel:Mi
00000200: 7820 4c65 7665 6c3a 3101 0000 0005 0000  x Level:1.......
00000210: 004d 7573 6963 0100 0000 1200 0000 4175  .Music........Au
00000220: 746f 4d69 784e 6f72 6d61 6c69 7a65 3a32  toMixNormalize:2
00000230: 0100 0000 1500 0000 4869 6768 6c69 6768  ........Highligh
00000240: 7446 6561 7475 7265 4d75 7369 6303 0000  tFeatureMusic...
00000250: 0017 0000 0054 7261 636b 4678 5365 7474  .....TrackFxSett
00000260: 696e 673a 4475 636b 3a32 3a32 0100 0000  ing:Duck:2:2....
00000270: 1f00 0000 5472 6163 6b46 7853 6574 7469  ....TrackFxSetti
00000280: 6e67 3a49 6e73 7472 756d 656e 7461 6c3a  ng:Instrumental:
00000290: 323a 350f 0000 0014 0000 004d 6978 4c65  2:5........MixLe
000002a0: 7665 6c3a 4d69 7820 4c65 7665 6c3a 3201  vel:Mix Level:2.
000002b0: 0000 0003 0000 0053 4658 0100 0000 1200  .......SFX......
000002c0: 0000 4175 746f 4d69 784e 6f72 6d61 6c69  ..AutoMixNormali
000002d0: 7a65 3a33 0100 0000 1700 0000 5472 6163  ze:3........Trac
000002e0: 6b46 7853 6574 7469 6e67 3a44 7563 6b3a  kFxSetting:Duck:
000002f0: 333a 3201 0000 0019 0000 004d 6163 726f  3:2........Macro
00000300: 4678 5365 7474 696e 673a 4d61 7869 6d69  FxSetting:Maximi
00000310: 7a65 3a33 0100 0000 1400 0000 4d69 784c  ze:3........MixL
00000320: 6576 656c 3a4d 6978 204c 6576 656c 3a33  evel:Mix Level:3
00000330: 0100 0000 0800 0000 416d 6269 656e 6365  ........Ambience
00000340: 0100 0000 1200 0000 4175 746f 4d69 784e  ........AutoMixN
00000350: 6f72 6d61 6c69 7a65 3a34 0100 0000 1700  ormalize:4......
00000360: 0000 4d61 6372 6f46 7853 6574 7469 6e67  ..MacroFxSetting
00000370: 3a53 7072 6561 643a 3401 0000 0014 0000  :Spread:4.......
00000380: 004d 6978 4c65 7665 6c3a 4d69 7820 4c65  .MixLevel:Mix Le
00000390: 7665 6c3a 3401 0000 0003 0000 0042 7573  vel:4........Bus
000003a0: 0100 0000 1000 0000 4661 6465 416e 6443  ........FadeAndC
000003b0: 726f 7373 4661 6465 0100 0000 2500 0000  rossFade....%...
000003c0: 4d61 6372 6f46 7853 6574 7469 6e67 3a4d  MacroFxSetting:M
000003d0: 756c 7469 6261 6e64 2043 6f6d 7072 6573  ultiband Compres
000003e0: 736f 723a 3701 0000 0010 0000 004f 7074  sor:7........Opt
000003f0: 696d 697a 6542 7573 4c65 7665 6c03 0000  imizeBusLevel...
00000400: 0007 0000 0046 6164 654f 7574 0900 0000  .....FadeOut....
00000410: 4800 0000 1300 0000 4175 746f 4d69 7853  H.......AutoMixS
00000420: 6f72 7441 6e64 4c61 6265 6c66 8866 7701  ortAndLabelf.fw.
00000430: 0000 003c 0000 0001 0000 00a1 7643 ff08  ...<........vC..
00000440: 0000 0044 6961 6c6f 6775 6500 6eeb ff05  ...Dialogue.n...
00000450: 0000 004d 7573 6963 a073 99ff 0300 0000  ...Music.s......
00000460: 5346 5877 a0c6 ff08 0000 0041 6d62 6965  SFXw.......Ambie
00000470: 6e63 6511 0000 0018 0000 0054 7261 636b  nce........Track
00000480: 4678 5365 7474 696e 673a 436c 6561 6e3a  FxSetting:Clean:
00000490: 313a 3066 8866 7701 0000 0005 0000 0001  1:0f.fw.........
000004a0: 0000 0000 3800 0000 1700 0000 4d61 6372  ....8.......Macr
000004b0: 6f46 7853 6574 7469 6e67 3a44 652d 6573  oFxSetting:De-es
000004c0: 733a 3166 8866 7701 0000 002c 0000 0002  s:1f.fw....,....
000004d0: 0000 0017 0000 0062 6d64 3a44 652d 4573  .......bmd:De-Es
000004e0: 7365 723a 3131 3132 3336 3030 3531 0800  ser:1112360051..
000004f0: 0000 4465 2d45 7373 6572 0011 0000 001c  ..De-Esser......
00000500: 0000 0054 7261 636b 4678 5365 7474 696e  ...TrackFxSettin
00000510: 673a 4c65 7665 6c6c 696e 673a 313a 3166  g:Levelling:1:1f
00000520: 8866 7701 0000 0005 0000 0001 0000 0000  .fw.............
00000530: 1100 0000 1500 0000 5472 6163 6b46 7853  ........TrackFxS
00000540: 6574 7469 6e67 3a45 513a 313a 3366 8866  etting:EQ:1:3f.f
00000550: 7701 0000 0005 0000 0001 0000 0000 1100  w...............
00000560: 0000 1b00 0000 5472 6163 6b46 7853 6574  ......TrackFxSet
00000570: 7469 6e67 3a44 796e 616d 6963 733a 313a  ting:Dynamics:1:
00000580: 3466 8866 7701 0000 0005 0000 0001 0000  4f.fw...........
00000590: 0000 1400 0000 1400 0000 4d69 784c 6576  ..........MixLev
000005a0: 656c 3a4d 6978 204c 6576 656c 3a31 6688  el:Mix Level:1f.
000005b0: 6677 0100 0000 0800 0000 0200 0000 0000  fw..............
000005c0: 0000 1100 0000 1700 0000 5472 6163 6b46  ..........TrackF
000005d0: 7853 6574 7469 6e67 3a44 7563 6b3a 323a  xSetting:Duck:2:
000005e0: 3266 8866 7701 0000 0005 0000 0001 0000  2f.fw...........
000005f0: 0000 1100 0000 1f00 0000 5472 6163 6b46  ..........TrackF
00000600: 7853 6574 7469 6e67 3a49 6e73 7472 756d  xSetting:Instrum
00000610: 656e 7461 6c3a 323a 3566 8866 7701 0000  ental:2:5f.fw...
00000620: 0005 0000 0001 0000 0000 1400 0000 1400  ................
00000630: 0000 4d69 784c 6576 656c 3a4d 6978 204c  ..MixLevel:Mix L
00000640: 6576 656c 3a32 6688 6677 0100 0000 0800  evel:2f.fw......
00000650: 0000 0200 0000 e2ff ffff 1100 0000 1700  ................
00000660: 0000 5472 6163 6b46 7853 6574 7469 6e67  ..TrackFxSetting
00000670: 3a44 7563 6b3a 333a 3266 8866 7701 0000  :Duck:3:2f.fw...
00000680: 0005 0000 0001 0000 0000 4400 0000 1900  ..........D.....
00000690: 0000 4d61 6372 6f46 7853 6574 7469 6e67  ..MacroFxSetting
000006a0: 3a4d 6178 696d 697a 653a 3366 8866 7701  :Maximize:3f.fw.
000006b0: 0000 0038 0000 0002 0000 0023 0000 0062  ...8.......#...b
000006c0: 6d64 3a4d 756c 7469 6261 6e64 2043 6f6d  md:Multiband Com
000006d0: 7072 6573 736f 723a 3131 3132 3336 3030  pressor:11123600
000006e0: 3433 0800 0000 4d61 7869 6d69 7365 0014  43....Maximise..
000006f0: 0000 0014 0000 004d 6978 4c65 7665 6c3a  .......MixLevel:
00000700: 4d69 7820 4c65 7665 6c3a 3366 8866 7701  Mix Level:3f.fw.
00000710: 0000 0008 0000 0002 0000 006a ffff ff40  ...........j...@
00000720: 0000 0017 0000 004d 6163 726f 4678 5365  .......MacroFxSe
00000730: 7474 696e 673a 5370 7265 6164 3a34 6688  tting:Spread:4f.
00000740: 6677 0100 0000 3400 0000 0200 0000 1b00  fw....4.........
00000750: 0000 626d 643a 5374 6572 656f 2057 6964  ..bmd:Stereo Wid
00000760: 7468 3a31 3131 3233 3630 3035 310c 0000  th:1112360051...
00000770: 0053 7465 7265 6f20 5769 6474 6800 1400  .Stereo Width...
00000780: 0000 1400 0000 4d69 784c 6576 656c 3a4d  ......MixLevel:M
00000790: 6978 204c 6576 656c 3a34 6688 6677 0100  ix Level:4f.fw..
000007a0: 0000 0800 0000 0200 0000 acfe ffff 5000  ..............P.
000007b0: 0000 2500 0000 4d61 6372 6f46 7853 6574  ..%...MacroFxSet
000007c0: 7469 6e67 3a4d 756c 7469 6261 6e64 2043  ting:Multiband C
000007d0: 6f6d 7072 6573 736f 723a 3766 8866 7701  ompressor:7f.fw.
000007e0: 0000 0044 0000 0002 0000 0023 0000 0062  ...D.......#...b
000007f0: 6d64 3a4d 756c 7469 6261 6e64 2043 6f6d  md:Multiband Com
00000800: 7072 6573 736f 723a 3131 3132 3336 3030  pressor:11123600
00000810: 3433 1400 0000 4d75 6c74 6962 616e 6420  43....Multiband 
00000820: 436f 6d70 7265 7373 6f72 0045 6469 7450  Compressor.EditP
00000830: 726f 6a65 6374 0000 0000 0000 0000 0000  roject..........
00000840: 0000 0000 0000 0000 0000 0001 0000 0066  ...............f
00000850: 8866 7701 0000 00c0 0000 0001 0000 0002  .fw.............
00000860: 0000 0001 0000 0002 0000 0000 0000 0000  ................
00000870: 0000 0000 0000 0000 0000 0001 0000 0005  ................
00000880: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000890: 0000 0000 0000 0006 0000 0034 1200 0003  ...........4....
000008a0: 0000 0007 0000 00e7 bc96 e7bb 8431 0700  .............1..
000008b0: 0000 e7bc 96e7 bb84 3207 0000 00e7 bc96  ........2.......
000008c0: e7bb 8433 0100 0000 1300 0000 e4b8 bbe6  ...3............
000008d0: b7b7 e99f b3ef bc88 4d61 696e efbc 8900  ........Main....
000008e0: 0000 0000 0000 0072 0500 0001 0000 0000  .......r........
000008f0: 0000 0000 0000 0000 0000 0078 0500 0001  ...........x....
00000900: 0000 0000 0000 0080 0500 0001 0000 0000  ................
00000910: 0000 0000 0000 0021 2100 0045 6666 6563  .......!!..Effec
00000920: 7443 6f6e 7465 7874 0000 0000 0000 0000  tContext........
00000930: 0000 0000 0000 0000 0000 0001 0000 0066  ...............f
00000940: 8866 7701 0000 0060 0100 000a 0000 0019  .fw....`........
00000950: 0000 000a 0000 0001 0000 0002 0000 00b4  ................
00000960: 0100 00d8 0200 00d9 0200 00da 0200 00db  ................
00000970: 0200 000f 0300 001e 0300 0020 0300 001a  ........... ....
00000980: 0000 0000 0000 001b 0000 0000 0000 001c  ................
00000990: 0000 0000 0000 001d 0000 0000 0000 001e  ................
000009a0: 0000 0009 0000 0077 0500 0078 0500 0079  .......w...x...y
000009b0: 0500 007a 0500 007b 0500 007c 0500 007d  ...z...{...|...}
000009c0: 0500 007e 0500 007f 0500 001f 0000 0007  ...~............
000009d0: 0000 0080 0500 0081 0500 0082 0500 0083  ................
000009e0: 0500 0084 0500 0085 0500 0086 0500 0020  ............... 
000009f0: 0000 0028 0000 0081 0500 0087 0500 0088  ...(............
00000a00: 0500 0089 0500 008a 0500 008b 0500 008c  ................
00000a10: 0500 008d 0500 008e 0500 008f 0500 0090  ................
00000a20: 0500 0091 0500 0092 0500 0093 0500 0094  ................
00000a30: 0500 0095 0500 0096 0500 0097 0500 0098  ................
00000a40: 0500 0099 0500 009a 0500 009b 0500 009c  ................
00000a50: 0500 009d 0500 009e 0500 009f 0500 00a0  ................
00000a60: 0500 00a1 0500 00a2 0500 00a3 0500 00a4  ................
00000a70: 0500 00a5 0500 00a6 0500 00a7 0500 00a8  ................
00000a80: 0500 00a9 0500 00aa 0500 00ab 0500 00ac  ................
00000a90: 0500 00ad 0500 0021 0000 0001 0000 0081  .......!........
00000aa0: 0500 0022 0000 0000 0000 0046 4c54 696d  ...".......FLTim
00000ab0: 656c 696e 6556 6965 7750 7265 7365 7473  elineViewPresets
00000ac0: 0000 0000 0000 0000 0000 0003 0000 0066  ...............f
00000ad0: 8866 7701 0000 00cd 0203 0003 0000 0000  .fw.............
00000ae0: 0000 0007 0000 0000 0000 0000 d008 0000  ................
00000af0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b00: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b10: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b20: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b30: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b40: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b50: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b60: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b70: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b80: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000b90: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ba0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000bb0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000bc0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000bd0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000be0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000bf0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c00: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c10: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c20: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c30: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c40: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c50: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c60: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c70: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c80: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000c90: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ca0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000cb0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000cc0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000cd0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ce0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000cf0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d00: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d10: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d20: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d30: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d40: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d50: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d60: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d70: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d80: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000d90: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000da0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000db0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000dc0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000dd0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000de0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000df0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e00: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e10: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e20: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e30: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e40: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e50: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e60: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e70: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e80: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000e90: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ea0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000eb0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ec0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ed0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ee0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ef0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f00: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f10: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f20: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f30: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f40: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f50: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f60: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f70: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f80: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000f90: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000fa0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000fb0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000fc0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000fd0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000fe0: 0000 0000 0000 0000 0000 0000 0000 0000  ................
00000ff0: 0000 0000 0000 0000 0000 0000 0000 0000  ................

## 文件内全部可读字符串（strings -n 3）

iCf
AdrDatabase
AutoMix
AutoMixMainf
Default
None
AutoMixClassify
AutoMixSortAndLabel
Dialogue
SeparateSpeakers
AutoMixNormalize:1
TrackFxSetting:Clean:1:0
MacroFxSetting:De-ess:1
TrackFxSetting:Levelling:1:1
TrackFxSetting:EQ:1:3
TrackFxSetting:Dynamics:1:4
MixLevel:Mix Level:1
Music
AutoMixNormalize:2
HighlightFeatureMusic
TrackFxSetting:Duck:2:2
TrackFxSetting:Instrumental:2:5
MixLevel:Mix Level:2
SFX
AutoMixNormalize:3
TrackFxSetting:Duck:3:2
MacroFxSetting:Maximize:3
MixLevel:Mix Level:3
Ambience
AutoMixNormalize:4
MacroFxSetting:Spread:4
MixLevel:Mix Level:4
Bus
FadeAndCrossFade
MacroFxSetting:Multiband Compressor:7
OptimizeBusLevel
FadeOut
AutoMixSortAndLabelf
Dialogue
Music
SFXw
Ambience
TrackFxSetting:Clean:1:0f
MacroFxSetting:De-ess:1f
bmd:De-Esser:1112360051
De-Esser
TrackFxSetting:Levelling:1:1f
TrackFxSetting:EQ:1:3f
TrackFxSetting:Dynamics:1:4f
MixLevel:Mix Level:1f
TrackFxSetting:Duck:2:2f
TrackFxSetting:Instrumental:2:5f
MixLevel:Mix Level:2f
TrackFxSetting:Duck:3:2f
MacroFxSetting:Maximize:3f
bmd:Multiband Compressor:1112360043
Maximise
MixLevel:Mix Level:3f
MacroFxSetting:Spread:4f
bmd:Stereo Width:1112360051
Stereo Width
MixLevel:Mix Level:4f
MacroFxSetting:Multiband Compressor:7f
bmd:Multiband Compressor:1112360043
Multiband Compressor
EditProject
Main
EffectContext
FLTimelineViewPresets
View
View
View
View
View
View
View
7UserViews
LastClient
D3"
Previewer
Generator
AmbisonicsRenderer
ADMRenderer
AIARenderer
ASAF Master
ASAF Object 
ASAF Scene!
ASAF Channels"
DolbyAtmosRenderer
Preview 1$
Preview 2%
Preview 3&
Preview 4'
Preview 5(
Preview 6)
Preview 7*
Preview 8+
Preview 9,
Preview 10-
Preview 11.
Preview 12/
Preview 130
Preview 141
Preview 152
Preview 163
Noise5
Beeps6
Timecode7
In 18
In 29
In 3:
In 4;
In 5<
In 6=
In 7>
In 8?
In 9@
In 10A
In 11B
In 12C
In 13D
In 14E
In 15F
In 16G
In 17H
In 18I
In 19J
In 20K
In 21L
In 22M
In 23N
In 24O
In 25P
In 26Q
In 27R
In 28S
In 29T
In 30U
In 31V
In 32W
In 33X
In 34Y
In 35Z
In 36[
Out-1\
Out-2]
Out-3^
Out-4_
Out-5`
Out-6a
Out-7b
Out-8c
Out-9d
Out-10e
Out-11f
Out-12g
Out-13h
Out-14i
Out-15j
Out-16k
Out-17l
Out-18m
Out-19n
Out-20o
Out-21p
Out-22q
Out-23r
Out-24s
Out-25t
Out-26u
Out-27v
Out-28w
Wall Materialx
Ceiling Materialy
Material AbsorptionScalez
Room SizeX{
Room SizeY|
Room SizeZ}
Grid Level~
Reverb Preset
Floor Material
RoomSimulation LateReverb
Post Reverb
Reverb Mix
Externalize Binaural
Headlock
Reverb
RoomSimulation
Rotation Yaw
Gain
Rotation Roll
Spatial Filter4 Azimuth
Rotation Pitch
Spatial Filter1 Enable
Spatial Filter1 Height
Spatial Filter4 Elevation
Spatial Filter3 Azimuth
Spatial Filter3 Elevation
Rotation Enable
Spatial Filter Enable
Mirror FrontBack
Spatial Filter4 Enable
Spatial Filter2 Elevation
Spatial Filter2 Azimuth
Spatial Filter4 Height
Spatial Filter1 Elevation
Spatial Filter1 Shape
Spatial Filter1 Width
Mirror UpDown
Spatial Filter2 Shape
Spatial Filter2 Width
Spatial Filter2 Enable
Spatial Filter3 Shape
Spatial Filter3 Width
Spatial Filter4 Shape
Spatial Filter4 Width
Gain Enable
Spatial Filter2 Height
Spatial Filter1 Azimuth
Spatial Filter4 FocalGain
Spatial Filter BaseGain
Spatial Filter3 FocalGain
Mirror LeftRight
SpatialFilter2 FocalGain
Spatial Filter3 Enable
Spatial Filter1 FocalGain
Spatial Filter3 Height
VO 1
VO 1
VO 2
VO 2
OS 3
OS 3
SFX 4
SFX 4
SFX 5
SFX 5
SFX 6
SFX 6
SFX 7
SFX 7
BGM 8
BGM 8
BGM 9
BGM 9
BGM 10
BGM 10
Mapping 1
Mapping 2
Mapping 3
Mapping 4
Mapping 5
Mapping 6
Mapping 7
Mapping 8
Mapping 9
Mapping 10
Mapping 11
Mapping 12
Mapping 13
Mapping 14
Mapping 15
Mapping 16
Mapping 17
Mapping 18
Mapping 19
Mapping 20
Mapping 21
Mapping 22
Mapping 23
Mapping 24
Mapping 25
Mapping 26
Mapping 27
Mapping 28
Mapping 29
Mapping 30
Mapping 31
Mapping 32
Mapping 33
Mapping 34
Mapping 35
Mapping 36
Mapping 37
Mapping 38
Mapping 39
Mapping 40
Mapping 41
Mapping 42
Mapping 43
Mapping 44
Mapping 45
Mapping 46
Mapping 47
Mapping 48
Mapping 49
Mapping 50
Mapping 51
Mapping 52
Mapping 53
Mapping 54
Mapping 55
Mapping 56
Mapping 57
Mapping 58
Mapping 59
Mapping 60
Mapping 61
Mapping 62
Mapping 63
Mapping 64
Mapping 65
Mapping 66
Mapping 67
Mapping 68
Mapping 69
Mapping 70
Mapping 71
Mapping 72
VCA 1
VCA 2
VCA 3
VCA 4
VCA 5
VCA 6
VCA 7
VCA 8
VCA 9
VCA 10
VCA 11
VCA 12
VCA 13
VCA 14
VCA 15
VCA 16
VCA 17
VCA 18
VCA 19
VCA 20
VCA 21
VCA 22
VCA 23
VCA 24
VCA 25
VCA 26
VCA 27
VCA 28
VCA 29
VCA 30
VCA 31
VCA 32
VCA 33
VCA 34
VCA 35
VCA 36
VCA 37
VCA 38
VCA 39
VCA 40
VCA 41
VCA 42
VCA 43
VCA 44
VCA 45
VCA 46
VCA 47
VCA 48
VCA 49
VCA 50
VCA 51
VCA 52
VCA 53
VCA 54
VCA 55
VCA 56
VCA 57
VCA 58
VCA 59
VCA 60
VCA 61
VCA 62
VCA 63
VCA 64
VCA 65
VCA 66
VCA 67
VCA 68
VCA 69
VCA 70
VCA 71
VCA 72
VCA 73
VCA 74
VCA 75
VCA 76
VCA 77
VCA 78
VCA 79
VCA 80
VCA 81
VCA 82
VCA 83
VCA 84
VCA 85
VCA 86
VCA 87
VCA 88
VCA 89
VCA 90
VCA 91
VCA 92
VCA 93
VCA 94
VCA 95
VCA 96
VCA 97
VCA 98
VCA 99
VCA 100
VCA 101
VCA 102
VCA 103
VCA 104
VCA 105
VCA 106
VCA 107
VCA 108
VCA 109
VCA 110
VCA 111
VCA 112
VCA 113
VCA 114
VCA 115
VCA 116
VCA 117
VCA 118
VCA 119
VCA 120
VCA 121
VCA 122
VCA 123
VCA 124
VCA 125
VCA 126
VCA 127
VCA 128
SFX
BGM
VO+SFX
Machine 1
Machine 2
Machine 3
Machine 4
Machine 5
All
SFX
BGM
Group 4
Group 5
Group 6
Group 7
Group 8
Group 9
Group 10
Group 11
Group 12
Group 13
Group 14
Group 15
Group 16
Group 17
Group 18
Group 19
Group 20
Group 21
Group 22
Group 23
Group 24
Group 25
Group 26
Group 27
Group 28
Group 29
Group 30
Group 31
Group 32
Group 33
Group 34
Group 35
Group 36
Group 37
Group 38
Group 39
Group 40
Group 41
Group 42
Group 43
Group 44
Group 45
Group 46
Group 47
Group 48
Group 49
Group 50
Group 51
Group 52
Group 53
Group 54
Group 55
Group 56
Group 57
Group 58
Group 59
Group 60
Group 61
Group 62
Group 63
Group 64
Group 65
Group 66
Group 67
Group 68
Group 69
Group 70
Group 71
Group 72
Group 73
Group 74
Group 75
Group 76
Group 77
Group 78
Group 79
Group 80
Group 81
Group 82
Group 83
Group 84
Group 85
Group 86
Group 87
Group 88
Group 89
Group 90
Group 91
Group 92
Group 93
Group 94
Group 95
Group 96
Group 97
Group 98
Group 99
Arial
Regular
