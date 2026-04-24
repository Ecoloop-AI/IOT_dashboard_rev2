"""
╔══════════════════════════════════════════════════════════════╗
║  NEXUS-2026  Industrial IoT Dashboard  — Production Ready    ║
║  Stack: Python · Dash · Plotly · Bootstrap · MQTT-Ready      ║
╚══════════════════════════════════════════════════════════════╝
"""

import dash
from dash import dcc, html, Input, Output, State, ctx, ALL
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
from datetime import datetime
import json, random, io, csv

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

# ════════════════════════════════════════════════════════════
# SENSOR REGISTRY — add/remove sensors here only
# ════════════════════════════════════════════════════════════
SENSORS = {
    "temp_1":    {"name":"Temperature","unit":"°C",    "icon":"🌡️","fa":"fa-thermometer-half","color":"#ff6b35","min":0,  "max":150,"nominal":72, "warn_h":100,"crit_h":120,"warn_l":40,"crit_l":20,"zone":"Reactor A"},
    "hum_1":     {"name":"Humidity",   "unit":"%RH",  "icon":"💧","fa":"fa-droplet",         "color":"#00d4ff","min":0,  "max":100,"nominal":55, "warn_h":75, "crit_h":90, "warn_l":25,"crit_l":10,"zone":"Cooling Tower"},
    "pres_1":    {"name":"Pressure",   "unit":"bar",  "icon":"⚡","fa":"fa-gauge-high",       "color":"#b347ff","min":0,  "max":16, "nominal":8,  "warn_h":12, "crit_h":14, "warn_l":2, "crit_l":1, "zone":"Pipeline B"},
    "flow_1":    {"name":"Flow Rate",  "unit":"L/min","icon":"🌊","fa":"fa-water",            "color":"#00ffb3","min":0,  "max":500,"nominal":250,"warn_h":400,"crit_h":450,"warn_l":50,"crit_l":20,"zone":"Pump Station"},
    "volt_1":    {"name":"Voltage",    "unit":"V",    "icon":"⚡","fa":"fa-bolt",             "color":"#ffd700","min":0,  "max":500,"nominal":380,"warn_h":420,"crit_h":450,"warn_l":340,"crit_l":300,"zone":"MCC Panel"},
    "curr_1":    {"name":"Current",    "unit":"A",    "icon":"🔌","fa":"fa-plug",             "color":"#ff9f43","min":0,  "max":100,"nominal":45, "warn_h":75, "crit_h":90, "warn_l":5, "crit_l":2, "zone":"Motor Drive"},
    "power_1":   {"name":"Power",      "unit":"kW",   "icon":"⚙️","fa":"fa-solar-panel",      "color":"#1dd1a1","min":0,  "max":50, "nominal":25, "warn_h":40, "crit_h":47, "warn_l":2, "crit_l":1, "zone":"Main Grid"},
    "rpm_1":     {"name":"Motor RPM",  "unit":"RPM",  "icon":"🔄","fa":"fa-gear",             "color":"#54a0ff","min":0,  "max":3600,"nominal":1800,"warn_h":3000,"crit_h":3400,"warn_l":200,"crit_l":50,"zone":"Compressor"},
    "level_1":   {"name":"Tank Level", "unit":"%",    "icon":"🧊","fa":"fa-fill-drip",        "color":"#5f27cd","min":0,  "max":100,"nominal":65, "warn_h":90, "crit_h":95, "warn_l":15,"crit_l":5, "zone":"Storage Tank"},
    "gas_1":     {"name":"Gas/AQI",    "unit":"ppm",  "icon":"💨","fa":"fa-wind",             "color":"#ff4757","min":0,  "max":1000,"nominal":150,"warn_h":400,"crit_h":700,"warn_l":0, "crit_l":0, "zone":"Exhaust Area"},
}

USERS = {
    "admin":    {"password":"admin123",    "role":"Administrator","color":"#ff6b35"},
    "operator": {"password":"operator123", "role":"Operator",     "color":"#00d4ff"},
    "viewer":   {"password":"viewer123",   "role":"Viewer",       "color":"#00ff9d"},
}

CONTROLS_DEF = {
    "relay_1": {"name":"Relay 1",    "type":"toggle","state":False},
    "relay_2": {"name":"Relay 2",    "type":"toggle","state":False},
    "motor_1": {"name":"Motor A",    "type":"toggle","state":False},
    "valve_1": {"name":"Main Valve", "type":"toggle","state":False},
    "pump_1":  {"name":"Pump 1",     "type":"toggle","state":False},
}

CHART_COLORS = ["#00d4ff","#00ff9d","#ff6b35","#b347ff","#ffd700","#ff4757","#1dd1a1","#54a0ff","#ff9f43","#5f27cd"]
DARK_TEMPLATE = "plotly_dark"
PLOT_BG       = "rgba(0,0,0,0)"
PAPER_BG      = "rgba(0,0,0,0)"
GRID_COLOR    = "rgba(0,212,255,0.07)"
FONT_FAMILY   = "Rajdhani, sans-serif"

# ════════════════════════════════════════════════════════════
# APP
# ════════════════════════════════════════════════════════════
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css",
    ],
    suppress_callback_exceptions=True,
    meta_tags=[{"name":"viewport","content":"width=device-width,initial-scale=1"}],
    title="NEXUS-2026 | Industrial IoT",
)
server = app.server

# ════════════════════════════════════════════════════════════
# DATA SIMULATION
# ════════════════════════════════════════════════════════════
MAX_HIST = 60

def simulate_value(sensor_id, prev=None):
    """Realistic random walk around nominal value."""
    s = SENSORS[sensor_id]
    nom = s["nominal"]
    span = s["max"] - s["min"]
    drift = random.gauss(0, span * 0.008)
    if prev is None:
        prev = nom + random.gauss(0, span * 0.05)
    val = max(s["min"], min(s["max"], prev + drift))
    return round(val, 2)

def get_status(sid, val):
    s = SENSORS[sid]
    if val >= s["crit_h"] or val <= s["crit_l"]:  return "CRIT"
    if val >= s["warn_h"] or val <= s["warn_l"]:   return "WARN"
    return "OK"

def status_color(status):
    return {"OK":"#00ff9d","WARN":"#ffb347","CRIT":"#ff3366","OFFLINE":"#666"}.get(status,"#888")

def make_empty_store():
    ts = datetime.now().strftime("%H:%M:%S")
    data = {"timestamps":[ts], "controls":{k:v["state"] for k,v in CONTROLS_DEF.items()},
            "slider_val":50, "estop":False, "alarms":[], "user":None}
    for sid, s in SENSORS.items():
        v = s["nominal"] + random.gauss(0, (s["max"]-s["min"])*0.03)
        v = round(max(s["min"], min(s["max"], v)), 2)
        data[sid] = [v]
    return data

# ════════════════════════════════════════════════════════════
# CHART HELPERS
# ════════════════════════════════════════════════════════════
def base_layout(title="", height=300):
    return dict(
        template=DARK_TEMPLATE, height=height,
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG,
        font=dict(family=FONT_FAMILY, color="#9ab8cc", size=11),
        title=dict(text=title, font=dict(family="Orbitron,monospace", size=12, color="#00d4ff"), x=0.01),
        xaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, showgrid=True),
        yaxis=dict(gridcolor=GRID_COLOR, zerolinecolor=GRID_COLOR, showgrid=True),
        legend=dict(bgcolor="rgba(0,0,0,0.3)", bordercolor="rgba(0,212,255,0.2)", borderwidth=1),
        margin=dict(l=40, r=20, t=36, b=30),
        hovermode="x unified",
    )

def make_gauge_fig(sid, val):
    s = SENSORS[sid]
    color = s["color"]
    status = get_status(sid, val)
    gauge_color = status_color(status)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=val,
        number=dict(font=dict(family="Orbitron,monospace", size=30, color=gauge_color), suffix=s["unit"]),
        delta=dict(reference=s["nominal"], relative=False,
                   increasing=dict(color="#ff3366"), decreasing=dict(color="#00ff9d")),
        gauge=dict(
            axis=dict(range=[s["min"], s["max"]], tickcolor="#4a6a80",
                      tickfont=dict(family="Share Tech Mono", size=9, color="#4a6a80"), nticks=6),
            bar=dict(color=gauge_color, thickness=0.3),
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            steps=[
                dict(range=[s["min"],           s["crit_l"]],  color="rgba(255,51,102,0.15)"),
                dict(range=[s["crit_l"],         s["warn_l"]],  color="rgba(255,179,71,0.1)"),
                dict(range=[s["warn_l"],          s["warn_h"]], color="rgba(0,255,157,0.07)"),
                dict(range=[s["warn_h"],          s["crit_h"]], color="rgba(255,179,71,0.1)"),
                dict(range=[s["crit_h"],          s["max"]],    color="rgba(255,51,102,0.15)"),
            ],
            threshold=dict(line=dict(color=gauge_color, width=3), thickness=0.85, value=val),
        ),
        title=dict(text=f"<b>{s['name']}</b><br><sup>{s['zone']}</sup>",
                   font=dict(family="Orbitron,monospace", size=12, color=color)),
    ))
    fig.update_layout(
        template=DARK_TEMPLATE, height=240,
        plot_bgcolor=PLOT_BG, paper_bgcolor=PAPER_BG,
        margin=dict(l=20, r=20, t=30, b=10),
    )
    return fig

# ════════════════════════════════════════════════════════════
# LAYOUT BUILDERS
# ════════════════════════════════════════════════════════════
def make_header(user_info=None):
    role_badge = html.Span()
    if user_info:
        role_badge = dbc.Badge(user_info["role"], color="info", className="ms-2",
                               style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"})
    return html.Div(className="nexus-header", children=[
        html.Div(className="nexus-logo", children=[
            "NEXUS", html.Span("INDUSTRIAL IoT PLATFORM")
        ]),
        html.Div([
            html.Span(className="header-status-dot status-online"),
            html.Span("LIVE", style={"fontSize":"11px","letterSpacing":"2px","color":"#00ff9d","fontFamily":"Orbitron,monospace"}),
            role_badge,
        ], className="d-flex align-items-center"),
        html.Div([
            html.Div(id="live-clock", className="header-clock"),
            html.Div(id="alarm-count-badge", className="ms-3"),
        ], className="d-flex align-items-center"),
    ])

def make_kpi_strip(data):
    vals = {sid: data[sid][-1] for sid in SENSORS if sid in data and data[sid]}
    total_warn = sum(1 for sid,v in vals.items() if get_status(sid,v)=="WARN")
    total_crit = sum(1 for sid,v in vals.items() if get_status(sid,v)=="CRIT")
    total_ok   = len(vals) - total_warn - total_crit
    power_val  = round(vals.get("power_1", 0), 1)
    temp_val   = round(vals.get("temp_1", 0), 1)
    rpm_val    = round(vals.get("rpm_1", 0))

    items = [
        ("SENSORS",    f"{len(vals)}", "#00d4ff"),
        ("ONLINE",     str(total_ok),  "#00ff9d"),
        ("WARNINGS",   str(total_warn),"#ffb347"),
        ("CRITICAL",   str(total_crit),"#ff3366"),
        ("POWER",      f"{power_val}kW","#ffd700"),
        ("TEMP",       f"{temp_val}°C", "#ff6b35"),
        ("RPM",        f"{rpm_val}",    "#54a0ff"),
        ("MQTT",       "READY" if MQTT_AVAILABLE else "SIM", "#b347ff"),
    ]
    cols = []
    for label, val, color in items:
        cols.append(dbc.Col(html.Div(className="kpi-item", children=[
            html.Div(val, className="kpi-value", style={"color": color}),
            html.Div(label, className="kpi-label"),
        ]), width="auto"))
    return html.Div(className="glass-card mb-2 py-1",
                    style={"borderRadius":"8px"},
                    children=[dbc.Row(cols, className="g-0 flex-nowrap overflow-auto")])

def make_sensor_cards(data):
    cards = []
    for sid, s in SENSORS.items():
        vals = data.get(sid, [s["nominal"]])
        val = round(vals[-1], 2) if vals else s["nominal"]
        prev = round(vals[-2], 2) if len(vals) > 1 else val
        status = get_status(sid, val)
        color  = s["color"]
        sc     = status_color(status)

        trend_icon = "▲" if val > prev else ("▼" if val < prev else "●")
        trend_cls  = "trend-up" if val > prev else ("trend-down" if val < prev else "trend-flat")

        badge_cls = {"OK":"badge-ok","WARN":"badge-warn","CRIT":"badge-crit"}.get(status,"badge-offline")

        cards.append(dbc.Col(
            html.Div(
                id={"type":"sensor-card","index":sid},
                className="sensor-card",
                n_clicks=0,
                style={"borderColor": f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.3)"},
                children=[
                    html.Div(className="card-glow-bar", style={"background": f"linear-gradient(90deg, {color}, transparent)"}),
                    dbc.Row([
                        dbc.Col([
                            html.Div(s["name"], className="sensor-name"),
                            html.Div([
                                html.Span(f"{val}", className="sensor-value", style={"color": sc}),
                                html.Span(s["unit"], className="sensor-unit"),
                            ], className="d-flex align-items-baseline"),
                            html.Div([
                                html.Span(status, className=f"status-badge {badge_cls}"),
                                html.Span(f" {trend_icon}", className=f"ms-2 {trend_cls}", style={"fontSize":"14px"}),
                            ], className="mt-2 d-flex align-items-center"),
                        ], width=8),
                        dbc.Col([
                            html.Div(s["icon"], className="sensor-icon", style={"color": color, "fontSize":"28px", "textAlign":"right"}),
                            html.Div(s["zone"], className="sensor-zone mt-2"),
                        ], width=4, className="text-end"),
                    ]),
                ],
            ),
            xs=6, sm=4, md=3, lg=2,
        ))

    return html.Div([
        html.Div("LIVE SENSOR MONITOR", className="section-title"),
        dbc.Row(cards, className="g-2"),
    ])

def make_realtime_chart(data):
    ts = data.get("timestamps", [])
    fig = go.Figure()
    for i, (sid, s) in enumerate(SENSORS.items()):
        vals = data.get(sid, [])
        if not vals: continue
        color = CHART_COLORS[i % len(CHART_COLORS)]
        fig.add_trace(go.Scatter(
            x=ts, y=vals, name=s["name"],
            line=dict(color=color, width=1.8, shape="spline"),
            fill="tozeroy",
            fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.04)",
            hovertemplate=f"<b>{s['name']}</b>: %{{y:.2f}} {s['unit']}<extra></extra>",
            visible=True if i < 4 else "legendonly",
        ))
    fig.update_layout(**base_layout("REAL-TIME SENSOR TRENDS", 320))
    return dcc.Graph(figure=fig, config={"displayModeBar":False}, className="w-100")

def make_bar_chart(data):
    sids = list(SENSORS.keys())
    vals = [round(data.get(sid,[SENSORS[sid]["nominal"]])[-1],2) for sid in sids]
    names = [SENSORS[sid]["name"] for sid in sids]
    pcts  = [min(100, round((v/SENSORS[sid]["max"])*100)) for sid,v in zip(sids,vals)]
    colors= [status_color(get_status(sid,v)) for sid,v in zip(sids,vals)]
    fig = go.Figure()
    fig.add_trace(go.Bar(x=names, y=pcts, name="Current %",
                         marker=dict(color=colors, opacity=0.8, line=dict(color=colors, width=1)),
                         hovertemplate="<b>%{x}</b><br>%{y:.1f}% of max<extra></extra>"))
    fig.add_trace(go.Scatter(x=names, y=[SENSORS[sid]["warn_h"]/SENSORS[sid]["max"]*100 for sid in sids],
                             name="Warn Threshold", mode="lines",
                             line=dict(color="#ffb347", width=1, dash="dot")))
    fig.update_layout(**base_layout("SENSOR UTILISATION (%)", 260))
    return dcc.Graph(figure=fig, config={"displayModeBar":False}, className="w-100")

def make_area_compare(data, sensor_ids=None):
    if sensor_ids is None:
        sensor_ids = list(SENSORS.keys())[:4]
    ts = data.get("timestamps", [])
    fig = go.Figure()
    for i, sid in enumerate(sensor_ids):
        s = SENSORS.get(sid)
        if not s: continue
        vals = data.get(sid, [])
        if not vals: continue
        color = CHART_COLORS[i % len(CHART_COLORS)]
        norm = [round((v - s["min"]) / max(1, s["max"] - s["min"]) * 100, 2) for v in vals]
        fig.add_trace(go.Scatter(
            x=ts, y=norm, name=s["name"],
            fill="tonexty" if i>0 else "tozeroy",
            line=dict(color=color, width=1.5, shape="spline"),
            fillcolor=f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.06)",
            hovertemplate=f"<b>{s['name']}</b>: %{{y:.1f}}%<extra></extra>",
        ))
    fig.update_layout(**base_layout("NORMALISED COMPARISON (% of range)", 270))
    return dcc.Graph(figure=fig, config={"displayModeBar":False}, className="w-100")

def make_control_panel(controls, slider_val=50, estop=False, role="viewer"):
    can_operate = role in ("Administrator","Operator")
    ctrl_cards = []
    for cid, c in CONTROLS_DEF.items():
        state = controls.get(cid, c["state"])
        label = "ON" if state else "OFF"
        btn_cls = "ctrl-btn active" if state else "ctrl-btn inactive"
        btn_color = "#00ff9d" if state else "#555"
        ctrl_cards.append(dbc.Col(
            html.Button(
                [html.I(className=f"fas {c['fa'] if hasattr(c,'fa') else 'fa-circle-dot'} me-2"),
                 c["name"], html.Span(f" [{label}]", style={"fontSize":"10px","opacity":"0.7"})],
                id={"type":"ctrl-btn","index":cid},
                className=btn_cls,
                disabled=not can_operate,
                style={"borderColor": btn_color, "color": btn_color},
            ),
            xs=6, md=4,
        ))

    return html.Div([
        html.Div("CONTROL PANEL", className="section-title"),
        dbc.Row([
            dbc.Col([
                dbc.Row(ctrl_cards, className="g-2"),
                html.Div("SPEED CONTROL", className="section-title mt-3"),
                dcc.Slider(id="speed-slider", min=0, max=100, step=1, value=slider_val,
                           marks={0:"0%",25:"25%",50:"50%",75:"75%",100:"100%"},
                           tooltip={"placement":"bottom","always_visible":True},
                           disabled=not can_operate,
                           className="mt-2"),
            ], md=9),
            dbc.Col([
                html.Div("EMERGENCY", className="section-title"),
                html.Div(className="d-flex justify-content-center mt-2",
                         children=[
                             html.Button(
                                 ["E", html.Br(), "STOP"],
                                 id="estop-btn",
                                 className="estop-btn",
                                 disabled=not can_operate,
                                 style={"background":"rgba(255,51,102,0.4)" if estop else "rgba(255,51,102,0.2)"},
                             )
                         ]),
                html.Div("ACTIVATED" if estop else "READY",
                         className="text-center mt-2",
                         style={"color":"#ff3366" if estop else "#00ff9d",
                                "fontFamily":"Orbitron,monospace","fontSize":"10px","letterSpacing":"2px"}),
            ], md=3),
        ]),
    ])

def make_alerts_panel(data):
    alarms = data.get("alarms", [])
    items = []
    for sid, s in SENSORS.items():
        vals = data.get(sid, [s["nominal"]])
        if not vals: continue
        val = vals[-1]
        status = get_status(sid, val)
        if status == "CRIT":
            items.append(html.Div(className="alert-item alert-crit", children=[
                html.I(className="fas fa-triangle-exclamation me-1"),
                html.Strong(f"{s['name']}: "),
                f"{val}{s['unit']} — CRITICAL THRESHOLD EXCEEDED",
                html.Span(datetime.now().strftime("%H:%M:%S"), className="alert-time"),
            ]))
        elif status == "WARN":
            items.append(html.Div(className="alert-item alert-warn", children=[
                html.I(className="fas fa-circle-exclamation me-1"),
                html.Strong(f"{s['name']}: "),
                f"{val}{s['unit']} — Warning limit",
                html.Span(datetime.now().strftime("%H:%M:%S"), className="alert-time"),
            ]))
    for a in list(reversed(alarms))[:5]:
        items.append(html.Div(className="alert-item alert-info", children=[
            html.I(className="fas fa-circle-info me-1"),
            html.Span(a.get("msg","Control action")),
            html.Span(a.get("time",""), className="alert-time"),
        ]))
    if not items:
        items = [html.Div(className="alert-item alert-info", children=[
            html.I(className="fas fa-check-circle me-1"), "All sensors within normal parameters."
        ])]
    return html.Div([
        html.Div("ALARMS & EVENTS", className="section-title"),
        html.Div(items, style={"maxHeight":"280px","overflowY":"auto"}),
    ])

def make_device_health(data):
    rows = []
    for sid, s in SENSORS.items():
        vals = data.get(sid, [s["nominal"]])
        val = vals[-1] if vals else s["nominal"]
        status = get_status(sid, val)
        pct = round((val - s["min"]) / max(1, s["max"] - s["min"]) * 100)
        bar_color = status_color(status)
        health = max(0, 100 - abs(pct - round((s["nominal"]-s["min"])/(s["max"]-s["min"])*100))*1.5)
        rows.append(html.Div(className="device-row", children=[
            html.Span(s["icon"], style={"fontSize":"16px","minWidth":"24px"}),
            html.Div([
                html.Div(s["name"], style={"fontSize":"11px","fontWeight":"600"}),
                html.Div(s["zone"], className="sensor-zone"),
            ], style={"minWidth":"100px"}),
            html.Div(className="device-bar-bg flex-grow-1", children=[
                html.Div(className="device-bar-fill",
                         style={"width":f"{health:.0f}%","background":bar_color}),
            ]),
            html.Span(f"{health:.0f}%", style={"fontSize":"11px","color":bar_color,
                                                 "fontFamily":"Share Tech Mono,monospace","minWidth":"40px","textAlign":"right"}),
            html.Span(status, className=f"status-badge ms-2 badge-{'ok' if status=='OK' else 'warn' if status=='WARN' else 'crit'}"),
        ]))
    return html.Div([
        html.Div("DEVICE HEALTH MONITOR", className="section-title"),
        html.Div(rows, style={"maxHeight":"380px","overflowY":"auto"}),
    ])

def make_scada_svg(data):
    """Animated SCADA-style pipeline overview (SVG)."""
    vals = {sid: data.get(sid,[SENSORS[sid]["nominal"]])[-1] for sid in SENSORS}
    pres_v = vals.get("pres_1", 8)
    flow_v = vals.get("flow_1", 250)
    temp_v = vals.get("temp_1", 72)
    lvl_v  = vals.get("level_1", 65)
    pump_on = data.get("controls",{}).get("pump_1", False)
    motor_on= data.get("controls",{}).get("motor_1", False)
    pres_c  = status_color(get_status("pres_1", pres_v))
    flow_c  = status_color(get_status("flow_1", flow_v))
    temp_c  = status_color(get_status("temp_1", temp_v))
    tank_h  = max(4, int(lvl_v * 0.8))
    fan_anim = "spin-fan 0.3s linear infinite" if motor_on else "none"
    pump_anim= "pulse 1s ease infinite" if pump_on else "none"
    flow_anim = "dash-flow 1.5s linear infinite" if flow_v > 100 else "dash-flow 4s linear infinite"

    svg_content = f"""
    <svg viewBox="0 0 800 380" xmlns="http://www.w3.org/2000/svg"
         style="width:100%;height:100%;font-family:Rajdhani,sans-serif">
      <defs>
        <filter id="glow"><feGaussianBlur stdDeviation="3" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <linearGradient id="tankGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#5f27cd" stop-opacity="0.9"/>
          <stop offset="100%" stop-color="#341c8a" stop-opacity="0.6"/>
        </linearGradient>
        <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
          <path d="M0,0 L0,6 L8,3 z" fill="rgba(0,212,255,0.6)"/>
        </marker>
      </defs>

      <!-- Background grid -->
      <rect width="800" height="380" fill="rgba(0,5,20,0.6)" rx="12"/>
      <text x="400" y="24" text-anchor="middle" fill="rgba(0,212,255,0.5)"
            font-size="11" letter-spacing="5" font-family="Orbitron,monospace">SCADA — PLANT OVERVIEW</text>

      <!-- REACTOR A (left) -->
      <rect x="40" y="60" width="80" height="100" rx="6"
            fill="rgba(255,107,53,0.12)" stroke="#ff6b35" stroke-width="1.5" filter="url(#glow)"/>
      <text x="80" y="90" text-anchor="middle" fill="#ff6b35" font-size="10" font-weight="700"
            font-family="Orbitron,monospace">REACTOR</text>
      <text x="80" y="105" text-anchor="middle" fill="#aaa" font-size="9">A-101</text>
      <text x="80" y="130" text-anchor="middle" fill="{temp_c}" font-size="13" font-weight="700"
            font-family="Orbitron,monospace">{temp_v:.1f}°C</text>
      <text x="80" y="145" text-anchor="middle" fill="#666" font-size="9">TEMP</text>

      <!-- Pipeline Reactor → Pump -->
      <line x1="120" y1="110" x2="220" y2="110" stroke="rgba(0,212,255,0.4)" stroke-width="6" stroke-linecap="round"/>
      <line x1="120" y1="110" x2="220" y2="110" stroke="rgba(0,212,255,0.7)" stroke-width="2"
            stroke-dasharray="12,8" style="animation:{flow_anim}"/>
      <text x="170" y="102" text-anchor="middle" fill="{flow_c}" font-size="10"
            font-family="Orbitron,monospace">{flow_v:.0f}</text>
      <text x="170" y="125" text-anchor="middle" fill="#555" font-size="8">L/min</text>

      <!-- PUMP STATION -->
      <circle cx="250" cy="110" r="30" fill="rgba(0,255,179,0.1)"
              stroke="#00ffb3" stroke-width="1.5" filter="url(#glow)"
              style="animation:{pump_anim}"/>
      <text x="250" y="107" text-anchor="middle" fill="#00ffb3" font-size="9" font-weight="700"
            font-family="Orbitron,monospace">PUMP</text>
      <text x="250" y="120" text-anchor="middle" fill="{'#00ff9d' if pump_on else '#555'}" font-size="8">
        {'● RUN' if pump_on else '○ STOP'}
      </text>

      <!-- Pipeline Pump → Pressure gauge -->
      <line x1="280" y1="110" x2="380" y2="110" stroke="rgba(0,212,255,0.4)" stroke-width="6" stroke-linecap="round"/>
      <line x1="280" y1="110" x2="380" y2="110" stroke="rgba(179,71,255,0.7)" stroke-width="2"
            stroke-dasharray="10,8" style="animation:{flow_anim}"/>

      <!-- PRESSURE GAUGE -->
      <circle cx="410" cy="110" r="28" fill="rgba(179,71,255,0.1)"
              stroke="#b347ff" stroke-width="1.5" filter="url(#glow)"/>
      <text x="410" y="107" text-anchor="middle" fill="#b347ff" font-size="9"
            font-family="Orbitron,monospace">PRES</text>
      <text x="410" y="121" text-anchor="middle" fill="{pres_c}" font-size="11" font-weight="700"
            font-family="Orbitron,monospace">{pres_v:.1f}</text>
      <text x="410" y="133" text-anchor="middle" fill="#555" font-size="8">bar</text>

      <!-- Pipeline → Tank -->
      <line x1="438" y1="110" x2="500" y2="110" stroke="rgba(0,212,255,0.4)" stroke-width="6" stroke-linecap="round"/>
      <line x1="438" y1="110" x2="500" y2="110" stroke="rgba(0,212,255,0.7)" stroke-width="2"
            stroke-dasharray="10,8" style="animation:{flow_anim}"/>
      <line x1="500" y1="110" x2="500" y2="160" stroke="rgba(0,212,255,0.4)" stroke-width="6" stroke-linecap="round"/>
      <line x1="500" y1="110" x2="500" y2="160" stroke="rgba(0,212,255,0.7)" stroke-width="2"
            stroke-dasharray="10,8" style="animation:{flow_anim}"/>

      <!-- STORAGE TANK -->
      <rect x="455" y="160" width="90" height="{int(80)}" rx="4"
            fill="rgba(95,39,205,0.08)" stroke="#5f27cd" stroke-width="1.5"/>
      <rect x="455" y="{160 + int(80) - tank_h}" width="90" height="{tank_h}" rx="0"
            fill="url(#tankGrad)" style="transition:height 1s"/>
      <!-- Tank level lines -->
      <line x1="455" y1="{int(160 + 80*0.25)}" x2="545" y2="{int(160 + 80*0.25)}"
            stroke="rgba(95,39,205,0.3)" stroke-width="0.5" stroke-dasharray="3,3"/>
      <line x1="455" y1="{int(160 + 80*0.5)}" x2="545" y2="{int(160 + 80*0.5)}"
            stroke="rgba(95,39,205,0.3)" stroke-width="0.5" stroke-dasharray="3,3"/>
      <line x1="455" y1="{int(160 + 80*0.75)}" x2="545" y2="{int(160 + 80*0.75)}"
            stroke="rgba(95,39,205,0.3)" stroke-width="0.5" stroke-dasharray="3,3"/>
      <text x="500" y="{160 + 40}" text-anchor="middle" fill="#5f27cd" font-size="9"
            font-family="Orbitron,monospace">TANK</text>
      <text x="500" y="{160 + 95}" text-anchor="middle" fill="#aaa" font-size="10"
            font-family="Orbitron,monospace">{lvl_v:.0f}%</text>

      <!-- MOTOR / FAN -->
      <circle cx="650" cy="110" r="35" fill="rgba(84,160,255,0.08)"
              stroke="#54a0ff" stroke-width="1.5" filter="url(#glow)"/>
      <text x="650" y="97" text-anchor="middle" fill="#54a0ff" font-size="9" font-weight="700"
            font-family="Orbitron,monospace">MOTOR</text>
      <!-- Fan blades -->
      <g transform="translate(650,113)" style="animation:{fan_anim}">
        <ellipse rx="12" ry="4" fill="rgba(84,160,255,0.6)" transform="rotate(0)"/>
        <ellipse rx="12" ry="4" fill="rgba(84,160,255,0.6)" transform="rotate(60)"/>
        <ellipse rx="12" ry="4" fill="rgba(84,160,255,0.6)" transform="rotate(120)"/>
        <circle r="3" fill="#54a0ff"/>
      </g>
      <text x="650" y="133" text-anchor="middle" fill="{'#00ff9d' if motor_on else '#555'}" font-size="8">
        {'● RUN' if motor_on else '○ STOP'}
      </text>

      <!-- Pipeline Pressure → Motor -->
      <line x1="545" y1="200" x2="650" y2="200" stroke="rgba(0,212,255,0.3)" stroke-width="4" stroke-linecap="round"/>
      <line x1="650" y1="145" x2="650" y2="200" stroke="rgba(0,212,255,0.3)" stroke-width="4" stroke-linecap="round"/>

      <!-- MCC PANEL -->
      <rect x="670" y="60" width="90" height="80" rx="6"
            fill="rgba(255,215,0,0.06)" stroke="#ffd700" stroke-width="1.2"/>
      <text x="715" y="82" text-anchor="middle" fill="#ffd700" font-size="9" font-weight="700"
            font-family="Orbitron,monospace">MCC PANEL</text>
      <text x="715" y="100" text-anchor="middle" fill="#aaa" font-size="11"
            font-family="Orbitron,monospace">{vals.get('volt_1',380):.0f}V</text>
      <text x="715" y="115" text-anchor="middle" fill="#888" font-size="9">VOLTAGE</text>
      <text x="715" y="130" text-anchor="middle" fill="#ff9f43" font-size="11"
            font-family="Orbitron,monospace">{vals.get('curr_1',45):.1f}A</text>
      <text x="715" y="145" text-anchor="middle" fill="#888" font-size="9">CURRENT</text>

      <!-- GAS SENSOR (bottom) -->
      <rect x="100" y="270" width="100" height="70" rx="6"
            fill="rgba(255,71,87,0.08)" stroke="#ff4757" stroke-width="1.2" filter="url(#glow)"/>
      <text x="150" y="292" text-anchor="middle" fill="#ff4757" font-size="9" font-weight="700"
            font-family="Orbitron,monospace">GAS / AQI</text>
      <text x="150" y="312" text-anchor="middle" fill="{status_color(get_status('gas_1', vals.get('gas_1',150)))}"
            font-size="14" font-weight="700" font-family="Orbitron,monospace">{vals.get('gas_1',150):.0f}</text>
      <text x="150" y="327" text-anchor="middle" fill="#555" font-size="9">ppm</text>

      <!-- Legend -->
      <rect x="0" y="340" width="800" height="40" fill="rgba(0,0,0,0.3)"/>
      <circle cx="30" cy="360" r="4" fill="#00ff9d"/>
      <text x="40" y="364" fill="#888" font-size="9">NORMAL</text>
      <circle cx="100" cy="360" r="4" fill="#ffb347"/>
      <text x="110" y="364" fill="#888" font-size="9">WARNING</text>
      <circle cx="175" cy="360" r="4" fill="#ff3366"/>
      <text x="185" y="364" fill="#888" font-size="9">CRITICAL</text>
      <line x1="260" y1="360" x2="295" y2="360" stroke="rgba(0,212,255,0.7)" stroke-width="2" stroke-dasharray="6,4"/>
      <text x="300" y="364" fill="#888" font-size="9">FLOW</text>
      <text x="700" y="364" fill="rgba(0,212,255,0.4)" font-size="8"
            font-family="Orbitron,monospace">NEXUS-2026 SCADA v2.0</text>
    </svg>
    """
    return html.Div([
        html.Div("SCADA PLANT OVERVIEW", className="section-title"),
        html.Div(
            html.Div(svg_content, style={"lineHeight":"0"}),
            className="glass-card p-0",
            style={"borderRadius":"12px","overflow":"hidden","minHeight":"380px"},
        ),
    ])

# ════════════════════════════════════════════════════════════
# LOGIN LAYOUT
# ════════════════════════════════════════════════════════════
login_layout = html.Div(className="login-page", children=[
    html.Div(className="login-card", children=[
        html.Div("NEXUS-2026", className="login-title"),
        html.Div("INDUSTRIAL IoT PLATFORM", className="login-subtitle"),
        dbc.Form([
            dbc.Stack([
                html.Div([
                    html.Label("USERNAME", style={"fontSize":"10px","letterSpacing":"2px","color":"#4a6a80","fontFamily":"Orbitron,monospace"}),
                    dbc.Input(id="login-user", type="text", placeholder="Enter username",
                              className="login-input", debounce=False),
                ]),
                html.Div([
                    html.Label("PASSWORD", style={"fontSize":"10px","letterSpacing":"2px","color":"#4a6a80","fontFamily":"Orbitron,monospace"}),
                    dbc.Input(id="login-pass", type="password", placeholder="Enter password",
                              className="login-input", debounce=False),
                ]),
                html.Div(id="login-error", style={"color":"#ff3366","fontSize":"12px","textAlign":"center"}),
                html.Button("ACCESS SYSTEM", id="login-btn", className="login-btn", n_clicks=0),
            ], gap=3),
        ]),
        html.Div([
            html.Div("DEFAULT CREDENTIALS", style={"fontSize":"9px","color":"#4a6a80","letterSpacing":"2px","marginTop":"20px","marginBottom":"8px","textAlign":"center"}),
            dbc.Row([
                dbc.Col(html.Div("admin / admin123", style={"fontSize":"11px","color":"#ff6b35","textAlign":"center","fontFamily":"Share Tech Mono,monospace"})),
                dbc.Col(html.Div("operator / operator123", style={"fontSize":"11px","color":"#00d4ff","textAlign":"center","fontFamily":"Share Tech Mono,monospace"})),
                dbc.Col(html.Div("viewer / viewer123", style={"fontSize":"11px","color":"#00ff9d","textAlign":"center","fontFamily":"Share Tech Mono,monospace"})),
            ]),
        ]),
    ]),
])

# ════════════════════════════════════════════════════════════
# MAIN DASHBOARD LAYOUT
# ════════════════════════════════════════════════════════════
def make_dashboard_layout():
    return html.Div(id="main-app", children=[
        make_header(),
        dcc.Interval(id="interval", interval=1500, n_intervals=0),
        dcc.Store(id="sensor-store", data=make_empty_store()),
        dcc.Store(id="auth-store",   data=None),
        dcc.Download(id="download-csv"),
        dcc.Download(id="download-pdf"),

        html.Div(id="page-content", children=[
            login_layout,
        ]),

        # Sensor Detail Modal
        dbc.Modal(id="sensor-modal", is_open=False, centered=True, size="lg", children=[
            dbc.ModalHeader(dbc.ModalTitle(id="modal-title", style={"fontFamily":"Orbitron,monospace","fontSize":"14px","color":"#00d4ff"})),
            dbc.ModalBody(id="modal-body"),
            dbc.ModalFooter(dbc.Button("CLOSE", id="close-modal", color="secondary",
                                        style={"fontFamily":"Orbitron,monospace","fontSize":"11px","letterSpacing":"2px"})),
        ]),
    ])

app.layout = make_dashboard_layout()

# ════════════════════════════════════════════════════════════
# CALLBACKS
# ════════════════════════════════════════════════════════════

# ── Clock ─────────────────────────────────────────────────
@app.callback(Output("live-clock","children"), Input("interval","n_intervals"))
def update_clock(_):
    return datetime.now().strftime("%H:%M:%S — %Y·%m·%d")

# ── Login ─────────────────────────────────────────────────
@app.callback(
    Output("page-content","children"),
    Output("auth-store","data"),
    Output("login-error","children"),
    Input("login-btn","n_clicks"),
    State("login-user","value"),
    State("login-pass","value"),
    State("auth-store","data"),
    prevent_initial_call=True,
)
def handle_login(_, username, password, current_auth):
    if current_auth: return dash.no_update, dash.no_update, ""
    if not username or not password:
        return dash.no_update, dash.no_update, "Enter username and password"
    u = USERS.get((username or "").lower())
    if not u or u["password"] != password:
        return dash.no_update, dash.no_update, "Invalid credentials"
    user_data = {"username": username.lower(), "role": u["role"], "color": u["color"]}
    return make_main_dashboard(), user_data, ""

def make_main_dashboard():
    return html.Div([
        # KPI bar
        html.Div(id="kpi-strip", className="px-3 pt-2"),
        dbc.Container(fluid=True, className="px-3 pb-3", children=[
            dbc.Tabs(id="main-tabs", active_tab="tab-live", className="mt-2", children=[

                # ── Tab 1: Live Dashboard ──────────────────────────
                dbc.Tab(label="LIVE DASHBOARD", tab_id="tab-live",
                        label_style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"}, children=[
                    html.Div(id="sensor-cards-div", className="mt-3"),
                    dbc.Row(className="mt-2 g-2", children=[
                        dbc.Col(html.Div(className="glass-card", children=[
                            html.Div("PRESSURE — LIVE GAUGE", className="section-title"),
                            html.Div(className="gauge-wrapper", children=[
                                dcc.Graph(id="gauge-pressure", config={"displayModeBar":False}, style={"height":"240px"}),
                            ]),
                        ]), md=6),
                        dbc.Col(html.Div(className="glass-card", children=[
                            html.Div("TEMPERATURE — LIVE GAUGE", className="section-title"),
                            html.Div(className="gauge-wrapper", children=[
                                dcc.Graph(id="gauge-temp", config={"displayModeBar":False}, style={"height":"240px"}),
                            ]),
                        ]), md=6),
                    ]),
                    html.Div(className="glass-card mt-2", children=[
                        html.Div(id="realtime-chart-div"),
                    ]),
                ]),

                # ── Tab 2: Analytics ───────────────────────────────
                dbc.Tab(label="ANALYTICS", tab_id="tab-analytics",
                        label_style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"}, children=[
                    dbc.Row(className="mt-3 g-2", children=[
                        dbc.Col(html.Div(className="glass-card", children=[html.Div(id="bar-chart-div")]), md=6),
                        dbc.Col(html.Div(className="glass-card", children=[html.Div(id="area-chart-div")]), md=6),
                    ]),
                ]),

                # ── Tab 3: Control Panel ───────────────────────────
                dbc.Tab(label="CONTROLS", tab_id="tab-controls",
                        label_style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"}, children=[
                    html.Div(className="glass-card mt-3", id="control-panel-div"),
                ]),

                # ── Tab 4: Alerts ──────────────────────────────────
                dbc.Tab(label="ALARMS", tab_id="tab-alarms",
                        label_style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"}, children=[
                    html.Div(className="glass-card mt-3", id="alerts-div"),
                ]),

                # ── Tab 5: SCADA ───────────────────────────────────
                dbc.Tab(label="SCADA", tab_id="tab-scada",
                        label_style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"}, children=[
                    html.Div(className="mt-3", id="scada-div"),
                ]),

                # ── Tab 6: Device Health ───────────────────────────
                dbc.Tab(label="HEALTH", tab_id="tab-health",
                        label_style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"}, children=[
                    html.Div(className="glass-card mt-3", id="health-div"),
                ]),

                # ── Tab 7: Reports ─────────────────────────────────
                dbc.Tab(label="REPORTS", tab_id="tab-reports",
                        label_style={"fontFamily":"Orbitron,monospace","fontSize":"9px","letterSpacing":"2px"}, children=[
                    html.Div(className="glass-card mt-3 p-4", children=[
                        html.Div("EXPORT & REPORTS", className="section-title"),
                        dbc.Row(className="mt-3 g-3", children=[
                            dbc.Col(html.Button([html.I(className="fas fa-file-csv me-2"),"EXPORT CSV"],
                                                id="btn-csv", className="ctrl-btn",
                                                style={"color":"#00ff9d","borderColor":"#00ff9d"}), md=3),
                            dbc.Col(html.Div([
                                html.Div("SELECT SENSORS FOR EXPORT:", style={"fontSize":"10px","color":"#4a6a80","letterSpacing":"2px","marginBottom":"8px"}),
                                dcc.Checklist(
                                    id="export-sensors",
                                    options=[{"label":f"  {s['name']}","value":sid} for sid,s in SENSORS.items()],
                                    value=list(SENSORS.keys()),
                                    style={"color":"#9ab8cc","fontSize":"13px"},
                                    labelStyle={"display":"block","marginBottom":"4px"},
                                ),
                            ]), md=4),
                        ]),
                    ]),
                ]),
            ]),
        ]),
    ])

# ── Data Engine (live update) ────────────────────────────
@app.callback(
    Output("sensor-store","data"),
    Input("interval","n_intervals"),
    State("sensor-store","data"),
    State("auth-store","data"),
)
def update_store(_, data, auth):
    if not auth: return data
    if data is None: data = make_empty_store()

    ts = datetime.now().strftime("%H:%M:%S")
    timestamps = data.get("timestamps",[])
    timestamps.append(ts)
    if len(timestamps) > MAX_HIST: timestamps = timestamps[-MAX_HIST:]
    data["timestamps"] = timestamps

    for sid in SENSORS:
        prev_vals = data.get(sid,[])
        prev = prev_vals[-1] if prev_vals else SENSORS[sid]["nominal"]
        new_val = simulate_value(sid, prev)
        prev_vals.append(new_val)
        if len(prev_vals) > MAX_HIST: prev_vals = prev_vals[-MAX_HIST:]
        data[sid] = prev_vals

    return data

# ── Render KPI / sensor cards / charts / gauges ──────────
@app.callback(
    Output("kpi-strip","children"),
    Output("sensor-cards-div","children"),
    Output("gauge-pressure","figure"),
    Output("gauge-temp","figure"),
    Output("realtime-chart-div","children"),
    Output("bar-chart-div","children"),
    Output("area-chart-div","children"),
    Output("alerts-div","children"),
    Output("scada-div","children"),
    Output("health-div","children"),
    Output("control-panel-div","children"),
    Output("alarm-count-badge","children"),
    Input("sensor-store","data"),
    State("auth-store","data"),
    prevent_initial_call=True,
)
def render_all(data, auth):
    if not data or not auth:
        empty = [dash.no_update]*12
        return empty

    role = auth.get("role","Viewer")
    pres_v = data.get("pres_1",[8])[-1]
    temp_v = data.get("temp_1",[72])[-1]

    # Alarm badge
    crit_count = sum(1 for sid in SENSORS if get_status(sid, data.get(sid,[SENSORS[sid]["nominal"]])[-1]) == "CRIT")
    warn_count  = sum(1 for sid in SENSORS if get_status(sid, data.get(sid,[SENSORS[sid]["nominal"]])[-1]) == "WARN")
    if crit_count:
        badge = dbc.Badge(f"🔴 {crit_count} CRITICAL", color="danger",
                          style={"fontFamily":"Orbitron,monospace","fontSize":"9px","animation":"blink 0.6s infinite"})
    elif warn_count:
        badge = dbc.Badge(f"⚠ {warn_count} WARN", color="warning", text_color="dark",
                          style={"fontFamily":"Orbitron,monospace","fontSize":"9px"})
    else:
        badge = dbc.Badge("✓ ALL OK", color="success",
                          style={"fontFamily":"Orbitron,monospace","fontSize":"9px"})

    controls = data.get("controls", {k:v["state"] for k,v in CONTROLS_DEF.items()})
    return (
        make_kpi_strip(data),
        make_sensor_cards(data),
        make_gauge_fig("pres_1", pres_v),
        make_gauge_fig("temp_1", temp_v),
        make_realtime_chart(data),
        make_bar_chart(data),
        make_area_compare(data),
        make_alerts_panel(data),
        make_scada_svg(data),
        make_device_health(data),
        make_control_panel(controls, data.get("slider_val",50), data.get("estop",False), role),
        badge,
    )

# ── Control toggle ───────────────────────────────────────
@app.callback(
    Output("sensor-store","data",allow_duplicate=True),
    Input({"type":"ctrl-btn","index":ALL},"n_clicks"),
    State("sensor-store","data"),
    State("auth-store","data"),
    prevent_initial_call=True,
)
def toggle_control(_, data, auth):
    if not ctx.triggered_id or not data or not auth: return dash.no_update
    if auth.get("role") == "Viewer": return dash.no_update
    cid = ctx.triggered_id["index"]
    controls = data.get("controls", {k:v["state"] for k,v in CONTROLS_DEF.items()})
    controls[cid] = not controls.get(cid, False)
    data["controls"] = controls
    alarms = data.get("alarms",[])
    alarms.append({"msg":f"{CONTROLS_DEF.get(cid,{}).get('name',cid)} → {'ON' if controls[cid] else 'OFF'}",
                   "time": datetime.now().strftime("%H:%M:%S")})
    data["alarms"] = alarms[-20:]
    return data

# ── E-STOP ────────────────────────────────────────────────
@app.callback(
    Output("sensor-store","data",allow_duplicate=True),
    Input("estop-btn","n_clicks"),
    State("sensor-store","data"),
    State("auth-store","data"),
    prevent_initial_call=True,
)
def toggle_estop(n, data, auth):
    if not n or not data or not auth: return dash.no_update
    if auth.get("role") == "Viewer": return dash.no_update
    data["estop"] = not data.get("estop", False)
    controls = data.get("controls", {})
    if data["estop"]:
        for k in controls: controls[k] = False
        data["controls"] = controls
    alarms = data.get("alarms",[])
    alarms.append({"msg": f"EMERGENCY STOP {'ACTIVATED' if data['estop'] else 'RESET'}",
                   "time": datetime.now().strftime("%H:%M:%S")})
    data["alarms"] = alarms[-20:]
    return data

# ── Slider ────────────────────────────────────────────────
@app.callback(
    Output("sensor-store","data",allow_duplicate=True),
    Input("speed-slider","value"),
    State("sensor-store","data"),
    prevent_initial_call=True,
)
def update_slider(val, data):
    if not data: return dash.no_update
    data["slider_val"] = val
    return data

# ── Sensor card click → modal ────────────────────────────
@app.callback(
    Output("sensor-modal","is_open"),
    Output("modal-title","children"),
    Output("modal-body","children"),
    Input("close-modal","n_clicks"),
    Input({"type":"sensor-card","index":ALL},"n_clicks"),
    State("sensor-store","data"),
    prevent_initial_call=True,
)
def open_sensor_modal(_, card_clicks, data):
    triggered = ctx.triggered_id
    if triggered == "close-modal": return False, "", ""
    if not any(card_clicks or []): return False, "", ""
    if not triggered or not isinstance(triggered, dict): return False, "", ""

    sid = triggered["index"]
    s = SENSORS.get(sid)
    if not s or not data: return False, "", ""

    vals = data.get(sid, [s["nominal"]])
    val = vals[-1] if vals else s["nominal"]
    ts  = data.get("timestamps",[])
    status = get_status(sid, val)
    sc = status_color(status)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ts, y=vals, name=s["name"],
        line=dict(color=s["color"], width=2, shape="spline"),
        fill="tozeroy",
        fillcolor=f"rgba({int(s['color'][1:3],16)},{int(s['color'][3:5],16)},{int(s['color'][5:7],16)},0.1)",
    ))
    fig.add_hline(y=s["warn_h"], line_dash="dot", line_color="#ffb347", annotation_text="WARN HIGH", annotation_font_size=9)
    fig.add_hline(y=s["warn_l"], line_dash="dot", line_color="#ffb347", annotation_text="WARN LOW",  annotation_font_size=9)
    fig.add_hline(y=s["crit_h"], line_dash="dash", line_color="#ff3366", annotation_text="CRIT HIGH", annotation_font_size=9)
    fig.update_layout(**base_layout(f"{s['name']} — Historical Trend", 300))

    body = html.Div([
        dbc.Row([
            dbc.Col([
                html.Div([
                    html.Span(f"{val:.2f}", style={"fontFamily":"Orbitron,monospace","fontSize":"40px","fontWeight":"700","color":sc}),
                    html.Span(s["unit"], style={"fontSize":"16px","color":"#6b8fa8","marginLeft":"8px"}),
                ]),
                html.Div(status, className=f"status-badge badge-{'ok' if status=='OK' else 'warn' if status=='WARN' else 'crit'} mt-2",
                         style={"fontSize":"12px"}),
                html.Hr(style={"borderColor":"rgba(0,212,255,0.15)"}),
                dbc.Row([
                    dbc.Col([html.Div("ZONE",    style={"fontSize":"9px","color":"#4a6a80","letterSpacing":"2px"}), html.Div(s["zone"],    style={"fontSize":"13px"})]),
                    dbc.Col([html.Div("MIN",     style={"fontSize":"9px","color":"#4a6a80","letterSpacing":"2px"}), html.Div(f"{s['min']}{s['unit']}", style={"fontSize":"13px"})]),
                    dbc.Col([html.Div("MAX",     style={"fontSize":"9px","color":"#4a6a80","letterSpacing":"2px"}), html.Div(f"{s['max']}{s['unit']}", style={"fontSize":"13px"})]),
                    dbc.Col([html.Div("NOMINAL", style={"fontSize":"9px","color":"#4a6a80","letterSpacing":"2px"}), html.Div(f"{s['nominal']}{s['unit']}", style={"fontSize":"13px"})]),
                ], className="g-2"),
            ], md=5),
            dbc.Col([
                dcc.Graph(figure=make_gauge_fig(sid, val), config={"displayModeBar":False}),
            ], md=7),
        ]),
        dcc.Graph(figure=fig, config={"displayModeBar":False}),
    ])

    return True, f"{s['icon']}  {s['name'].upper()}  —  {s['zone']}", body

# ── CSV Export ────────────────────────────────────────────
@app.callback(
    Output("download-csv","data"),
    Input("btn-csv","n_clicks"),
    State("sensor-store","data"),
    State("export-sensors","value"),
    prevent_initial_call=True,
)
def export_csv(n, data, selected):
    if not n or not data: return dash.no_update
    buf = io.StringIO()
    writer = csv.writer(buf)
    header = ["Timestamp"] + [SENSORS[sid]["name"] + f" ({SENSORS[sid]['unit']})" for sid in (selected or SENSORS)]
    writer.writerow(header)
    ts_list = data.get("timestamps",[])
    for i, ts in enumerate(ts_list):
        row = [ts] + [data.get(sid,[0])[i] if i < len(data.get(sid,[])) else "" for sid in (selected or SENSORS)]
        writer.writerow(row)
    return dict(content=buf.getvalue(), filename=f"nexus_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")

# ════════════════════════════════════════════════════════════
# MQTT STUB (wire up your broker here)
# ════════════════════════════════════════════════════════════
def setup_mqtt(broker="localhost", port=1883):
    if not MQTT_AVAILABLE: return
    client = mqtt.Client()
    def on_message(client, userdata, msg):
        del client, userdata
        try:
            json.loads(msg.payload)  # parsed payload — wire to store in production
        except Exception:
            pass
    client.on_message = on_message
    client.connect(broker, port, 60)
    for sid in SENSORS:
        client.subscribe(f"iot/sensors/{sid}")
    client.loop_start()

# ════════════════════════════════════════════════════════════
# ENTRY POINT
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("""
    ╔══════════════════════════════════════════════════════╗
    ║   NEXUS-2026 Industrial IoT Dashboard                ║
    ║   → http://127.0.0.1:8050                            ║
    ║   Credentials: admin/admin123  operator/operator123  ║
    ╚══════════════════════════════════════════════════════╝
    """)
    server = app.server
