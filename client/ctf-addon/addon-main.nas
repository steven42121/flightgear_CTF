######################################################################
# MAYDAY CTF addon · 入口（FG 通过 --addon 加载本目录）
#
# FG 的加载机制（wiki Addon/Add-on initialization）：
#   * addon-main.nas 被装入命名空间 __addon[org.gkp2026.ctf]__
#   * 随后调用本文件的 main(addonGhost)
# 本 addon 不 fork FG、不做本地判定；所有判定在判决服务器。
# 客户端职责只有两件事：
#   1) 训练/正式模式开关 + 运行状态 HUD
#   2) 把属性树状态经 generic 遥测（Protocol/ctf-telemetry.xml）发出去，
#      与 multiplayer 位置包互补（MP 无 wow/AGL/指针等字段）
######################################################################

var CTF_MODE_PROP = "/ctf/mode";            # training | competitive
var CTF_STATUS_PROP = "/ctf/status";        # ok | suspect | banned
var CTF_TEL_CFG = "/ctf/telemetry/enabled"; # 遥测开关（正式模式必须开）
var CTF_UUID_PROP = "/sim/ctf/instance-uuid";  # FG instance identity

# 判决服务器的遥测出口（--generic 参数由 launcher.sh 带上，见 launcher）
var DEFAULT_TEL_HOST = "127.0.0.1";
var DEFAULT_TEL_PORT = 5510;

# ---------------- 训练模式 ----------------
# 训练模式：可以随意玩（--fdm=external、传送、改属性都行），
# 但 **不产生任何对外证据**。实现方式：把遥测 generic 输出节点关掉
# （enabled=0 时 launcher 不加 --generic 参数，本文件仅作运行时兜底）。
var apply_mode = func(mode) {
  if (mode == "training") {
    setprop(CTF_TEL_CFG, 0);
    setprop(CTF_STATUS_PROP, "ok");
    print("[CTF] 训练模式：不产出证据，允许任意实验。");
  } else {
    setprop(CTF_TEL_CFG, 1);
    print("[CTF] 正式模式：遥测开启，所有状态由服务器观测。");
  }
};

# ---------------- 遥测桥 ----------------
# generic 协议的 chunk 源属性（Protocol/ctf-telemetry.xml 引用这些节点）。
# FG 自带状态（position/orientation/velocities）无需桥接；
# 这里补齐服务器需要的"证据"节点：wow、ILS 指针、AGL（供属性树查询）。
var bridge_props = func {
  # 地轮指示（JSBSim 机型已有 /gear/gear[n]/wow；这里兜底复制到统一节点）
  var wow = 0;
  foreach (var g; props.globals.getNode("gear", 1).getChildren("gear")) {
    if (g.getNode("wow", 1).getBoolValue()) { wow = 1; }
  }
  setprop("/ctf/evidence/wow", wow);
  # NAV1 指针（若机型已有则直接复制，便于遥测统一读取）
  var nav = props.globals.getNode("instrumentation/nav[0]", 1);
  setprop("/ctf/evidence/nav-hdg-deflection",
          nav.getNode("heading-needle-deflection", 1).getValue());
  setprop("/ctf/evidence/nav-gs-norm",
          nav.getNode("gs-needle-deflection-norm", 1).getValue());
};

# ---------------- FG Instance UUID ---------------- 
# 生成一次性随机 UUID，绑定到 /sim/ctf/instance-uuid。
# 反作弊通过 telnet 读它签进心跳，服务端通过遥测和心跳交叉比对，
# 防止"两台机子各跑一半"攻击。
var _gen_uuid = func {
  var chars = "0123456789abcdef";
  var uuid = "";
  for (var i = 0; i < 32; i += 1) {
    uuid ~= chr(chars, rand() % 16);
    if (i == 7 or i == 11 or i == 15 or i == 19) { uuid ~= "-"; }
  }
  setprop(CTF_UUID_PROP, uuid);
  print("[CTF] Instance UUID: ", uuid);
};

# ---------------- 启动入口 ----------------
var main = func(addonGhost) {
  print("[CTF] MAYDAY addon loaded. mode=",
        getprop(CTF_MODE_PROP) or "training");
  _gen_uuid();
  var mode = getprop(CTF_MODE_PROP) or "training";
  apply_mode(mode);
  # 每 0.5s 刷新一次证据节点
  settimer(bridge_props_loop, 0.5);
};

var bridge_props_loop = func {
  bridge_props();
  settimer(bridge_props_loop, 0.5);
};