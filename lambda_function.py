# lambda_function.py
# SNS → Lambda → Slack (CloudWatch Alarm)
# - Slack 메시지를 한국어/깔끔한 Block UI로 전송
# - UTC 시간(StateChangeTime)을 DISPLAY_TZ(기본 Asia/Seoul)로 변환

import json
import os
import re
import time
import urllib.request
import urllib.error
from urllib.parse import quote
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# ===== 환경 변수 =====
WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL")  # 필수
SLACK_CHANNEL = os.environ.get("SLACK_CHANNEL")
SLACK_USERNAME = os.environ.get("SLACK_USERNAME", "CloudWatch 경보")
SLACK_ICON_EMOJI = os.environ.get("SLACK_ICON_EMOJI", ":rotating_light:")
DISPLAY_TZ_NAME = os.environ.get("DISPLAY_TZ", "Asia/Seoul")  # 표기/변환에 사용
SHOW_UTC = os.environ.get("SHOW_UTC", "false").lower() == "true"

# ===== 색상/라벨 =====
STATE_COLOR = {
    "ALARM": "#E01E5A",            # 빨강
    "OK": "#2EB67D",               # 초록
    "INSUFFICIENT_DATA": "#ECB22E" # 노랑
}
STATE_KO = {
    "ALARM": "경보",
    "OK": "정상",
    "INSUFFICIENT_DATA": "데이터 부족"
}
STATE_EMOJI = {
    "ALARM": "🚨",
    "OK": "✅",
    "INSUFFICIENT_DATA": "❔"
}
CMP_KO = {
    "GreaterThanOrEqualToThreshold": "≥",
    "GreaterThanThreshold": ">",
    "LessThanThreshold": "<",
    "LessThanOrEqualToThreshold": "≤"
}

try:
    DISPLAY_TZ = ZoneInfo(DISPLAY_TZ_NAME)
except Exception:
    DISPLAY_TZ_NAME = "Asia/Seoul"
    DISPLAY_TZ = ZoneInfo(DISPLAY_TZ_NAME)

# ---------- 유틸 ----------

def _safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        return None

def _parse_to_tz(dt_str: Optional[str]) -> Optional[str]:
    """CloudWatch StateChangeTime(UTC)을 DISPLAY_TZ로 변환."""
    if not dt_str:
        return None
    s = dt_str.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    m = re.search(r"([+-])(\d{2})(\d{2})$", s)
    if m:
        s = s[:m.start()] + f"{m.group(1)}{m.group(2)}:{m.group(3)}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        s2 = re.sub(r"\.\d{3,6}", "", s)
        dt = datetime.fromisoformat(s2)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(DISPLAY_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")

def _extract_first_value_from_reason(reason: Optional[str]) -> Optional[str]:
    """CloudWatch Reason에서 최근 데이터포인트 값을 추출(있으면). 예: '[85.0]' → 85.0"""
    if not reason:
        return None
    m = re.search(r"\[(\d+(?:\.\d+)?)\]", reason)
    return m.group(1) if m else None

def _alarm_console_url(region: str, alarm_name: Optional[str]) -> Optional[str]:
    if not region or not alarm_name:
        return None
    # 알람 콘솔 바로가기
    name_enc = quote(alarm_name, safe="")
    return f"https://{region}.console.aws.amazon.com/cloudwatch/home?region={region}#alarmsV2:alarm/{name_enc}"

def _extract_alarm_info(sns_record: Dict[str, Any]) -> Dict[str, Any]:
    """SNS 레코드에서 CloudWatch Alarm 정보를 표준 구조로 변환."""
    S = sns_record.get("Sns", {})
    subject = S.get("Subject")
    message_str = S.get("Message", "")
    region = S.get("TopicArn", "arn:aws:sns:::").split(":")[3] or "unknown"

    msg_json = _safe_json_loads(message_str)
    if msg_json:
        alarm_name = msg_json.get("AlarmName")
        new_state = (msg_json.get("NewStateValue") or "").upper()
        reason = msg_json.get("NewStateReason")
        time_iso = msg_json.get("StateChangeTime")
        alarm_arn = msg_json.get("AlarmArn")
        trigger = msg_json.get("Trigger", {}) or {}

        metric_name = trigger.get("MetricName")
        namespace = trigger.get("Namespace")
        stat = trigger.get("Statistic") or trigger.get("Stat")
        comparison = trigger.get("ComparisonOperator")
        threshold = trigger.get("Threshold")
        period = trigger.get("Period")
        eval_periods = trigger.get("EvaluationPeriods")
        dimensions = trigger.get("Dimensions") or []
        dims = {d.get("name") or d.get("Name"): d.get("value") or d.get("Value") for d in dimensions if d}

        latest_value = _extract_first_value_from_reason(reason)
        return {
            "subject": subject or f"[{STATE_KO.get(new_state, new_state)}] {alarm_name}",
            "region": region,
            "alarm_name": alarm_name,
            "new_state": new_state,
            "reason": reason,
            "time_utc": time_iso,
            "time_tz": _parse_to_tz(time_iso),
            "alarm_arn": alarm_arn,
            "metric_name": metric_name,
            "namespace": namespace,
            "statistic": stat,
            "comparison": comparison,
            "threshold": threshold,
            "latest_value": latest_value,
            "period": period,
            "evaluation_periods": eval_periods,
            "dimensions": dims,
            "console_url": _alarm_console_url(region, alarm_name),
            "raw": msg_json,
        }
    else:
        return {
            "subject": subject or "CloudWatch 경보 알림",
            "region": region,
            "alarm_name": None,
            "new_state": None,
            "reason": message_str,
            "time_utc": None,
            "time_tz": None,
            "alarm_arn": None,
            "metric_name": None,
            "namespace": None,
            "statistic": None,
            "comparison": None,
            "threshold": None,
            "latest_value": None,
            "period": None,
            "evaluation_periods": None,
            "dimensions": {},
            "console_url": None,
            "raw": message_str,
        }

def _build_slack_blocks(info: Dict[str, Any]) -> Dict[str, Any]:
    state = (info.get("new_state") or "").upper()
    title = info["subject"] or "CloudWatch 경보 알림"
    color = STATE_COLOR.get(state, "#439FE0")
    emoji = STATE_EMOJI.get(state, "🔔")
    state_ko = STATE_KO.get(state, state or "알 수 없음")

    # 핵심 요약 한 줄
    headline = f"{emoji} *{state_ko}* — `{info.get('alarm_name') or '알람'}`"

    # 대상(InstanceId 등) 요약
    target_text = None
    if info.get("dimensions"):
        # 대표적으로 InstanceId, AutoScalingGroupName 우선
        iid = info["dimensions"].get("InstanceId")
        asg = info["dimensions"].get("AutoScalingGroupName")
        if iid and asg:
            target_text = f"*대상:* `{iid}` (ASG: `{asg}`)"
        elif iid:
            target_text = f"*대상:* `{iid}`"
        elif asg:
            target_text = f"*대상 ASG:* `{asg}`"

    # 지표/임계 요약
    cmp_symbol = CMP_KO.get(info.get("comparison") or "", "")
    metric_line = None
    if info.get("metric_name") and info.get("namespace"):
        metric_line = f"*지표:* `{info['namespace']}/{info['metric_name']}`"
    threshold_line = None
    if cmp_symbol and info.get("threshold") is not None:
        latest = f" / 최신값: *{info['latest_value']}*" if info.get("latest_value") else ""
        threshold_line = f"*임계값:* {cmp_symbol} *{info['threshold']}*{latest}"

    meta1 = []
    if info.get("time_tz"):
        meta1.append(f"*시간({DISPLAY_TZ_NAME}):* {info['time_tz']}")
    elif info.get("time_utc"):
        meta1.append(f"*시간(UTC):* {info['time_utc']}")
    if SHOW_UTC and info.get("time_utc"):
        meta1.append(f"*UTC:* {info['time_utc']}")
    if info.get("region"):
        meta1.append(f"*리전:* `{info['region']}`")

    meta2 = []
    if info.get("statistic"):
        meta2.append(f"*통계:* `{info['statistic']}`")
    if info.get("period"):
        meta2.append(f"*주기:* `{info['period']}s`")
    if info.get("evaluation_periods"):
        meta2.append(f"*평가 구간:* `{info['evaluation_periods']}`")

    # Reason (길면 자름)
    reason = info.get("reason")
    if isinstance(reason, str) and len(reason) > 2900:
        reason = reason[:2900] + " …(생략)"

    blocks = [
        {"type": "header", "text": {"type": "plain_text", "text": title[:150], "emoji": True}},
        {"type": "section", "text": {"type": "mrkdwn", "text": headline}},
    ]

    details_fields = []
    if target_text:
        details_fields.append({"type": "mrkdwn", "text": target_text})
    if metric_line:
        details_fields.append({"type": "mrkdwn", "text": metric_line})
    if threshold_line:
        details_fields.append({"type": "mrkdwn", "text": threshold_line})
    if details_fields:
        blocks.append({"type": "section", "fields": details_fields})

    meta_lines = []
    if meta1:
        meta_lines.append(" • ".join(meta1))
    if meta2:
        meta_lines.append(" • ".join(meta2))
    if meta_lines:
        blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": line} for line in meta_lines]})

    if reason:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*상태 사유:*\n{reason}"}})

    context_elems = []
    if info.get("alarm_arn"):
        context_elems.append({"type": "mrkdwn", "text": f"*ARN:* `{info['alarm_arn']}`"})
    if info.get("console_url"):
        context_elems.append({"type": "mrkdwn", "text": f"<{info['console_url']}|CloudWatch 알람 열기>"})
    if context_elems:
        blocks.append({"type": "context", "elements": context_elems})

    payload: Dict[str, Any] = {
        "username": SLACK_USERNAME,
        "icon_emoji": SLACK_ICON_EMOJI,
        "attachments": [{
            "color": color,
            "blocks": blocks
        }]
    }
    if SLACK_CHANNEL:
        payload["channel"] = SLACK_CHANNEL
    return payload

def _post_to_slack(payload: Dict[str, Any], max_retries: int = 4, base_sleep: float = 0.7) -> None:
    if not WEBHOOK_URL:
        raise RuntimeError("SLACK_WEBHOOK_URL is not set")
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.getcode() == 200:
                    return
                status = resp.getcode()
                if status in (429, 500, 502, 503, 504):
                    raise urllib.error.HTTPError(req.full_url, status, f"HTTP {status}", resp.headers, None)
                raise RuntimeError(f"Slack webhook returned status {status}")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                ra = e.headers.get("Retry-After")
                sleep_s = float(ra) if ra and ra.isdigit() else base_sleep * (2 ** attempt)
                time.sleep(sleep_s); continue
            if e.code in (500, 502, 503, 504):
                time.sleep(base_sleep * (2 ** attempt)); continue
            raise
        except urllib.error.URLError:
            time.sleep(base_sleep * (2 ** attempt)); continue
    raise RuntimeError("Failed to post to Slack after retries")

# ---------- Lambda 핸들러 ----------
def lambda_handler(event, context):
    records = event.get("Records", [])
    if not records:
        test_msg = _safe_json_loads(json.dumps(event)) or {"message": str(event)}
        payload = _build_slack_blocks({
            "subject": "Lambda 테스트/직접 호출",
            "region": "unknown",
            "reason": json.dumps(test_msg)[:2900]
        })
        _post_to_slack(payload)
        return {"ok": True, "sent": 1, "note": "No SNS records; sent generic payload."}

    sent = 0
    for r in records:
        info = _extract_alarm_info(r)
        payload = _build_slack_blocks(info)
        _post_to_slack(payload)
        sent += 1
    return {"ok": True, "sent": sent}
