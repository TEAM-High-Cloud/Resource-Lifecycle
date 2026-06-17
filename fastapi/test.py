from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openstack
import os
import re
import logging
import traceback

from keystoneauth1.identity import v3
from keystoneauth1 import session as ks_session

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI()

DOMAIN_NAME = "highcloud"

def get_domain_id(conn=None):
    conn = conn or get_conn()
    domain = conn.identity.find_domain(DOMAIN_NAME)
    if not domain:
        raise HTTPException(status_code=500, detail=f"'{DOMAIN_NAME}' 도메인을 찾을 수 없습니다.")
    return domain.id

def load_openrc(path="~/highcloud-admin-openrc.sh"):
    with open(os.path.expanduser(path)) as f:
        content = f.read()
    for match in re.finditer(r'export\s+(\w+)="?([^"\n]+)"?', content):
        key, value = match.group(1), match.group(2)
        os.environ[key] = value

def get_conn():
    load_openrc()
    return openstack.connect()

def verify_user_password(username: str, password: str) -> bool:
    """대상 유저의 username/password로 Keystone 토큰 발급을 시도해서 비번이 맞는지 확인."""
    load_openrc()
    auth_url = os.environ.get("OS_AUTH_URL")
    if not auth_url:
        raise HTTPException(status_code=500, detail="OS_AUTH_URL이 설정되지 않았습니다.")
    auth = v3.Password(
        auth_url=auth_url,
        username=username,
        password=password,
        user_domain_id=get_domain_id(),
        unscoped=True,
    )
    sess = ks_session.Session(auth=auth)
    try:
        token = sess.get_token()
        return bool(token)
    except Exception:
        # 인증 실패(비번 불일치 등)
        logger.info("password verify failed: user=%s", username)
        return False


# ── 요청 모델 ──────────────────────────────

class CreateProjectRequest(BaseModel):
    project_name: str
    user_id: str
    email: str
    password: str

class AddUserRequest(BaseModel):
    project_name: str
    user_id: str
    email: str
    password: str

class DeleteUserRequest(BaseModel):
    project_name: str
    user_id: str

class DeleteProjectRequest(BaseModel):
    project_name: str

class VerifyPasswordRequest(BaseModel):
    user_id: str
    password: str


# ── 비밀번호 검증 ──────────────────────────────

@app.post("/verify-password")
def verify_password(req: VerifyPasswordRequest):
    conn = get_conn()
    user = conn.identity.find_user(req.user_id)
    if not user:
        # 유저가 아예 없으면 검증 실패로 처리 (valid=False)
        return {"status": "success", "valid": False, "reason": "user_not_found"}
    valid = verify_user_password(req.user_id, req.password)
    return {"status": "success", "valid": valid}


# ── Form 1: 프로젝트 생성 + 리더 유저 생성 ──────────────────────────────

@app.post("/create")
def create_project_and_user(req: CreateProjectRequest):
    conn = get_conn()
    try:
        existing_project = conn.identity.find_project(req.project_name)
        if existing_project:
            raise HTTPException(status_code=409, detail="이미 존재하는 프로젝트명입니다.")

        project = conn.identity.create_project(
            name=req.project_name,
            domain_id=get_domain_id(conn)
        )

        is_new_user = False
        user = conn.identity.find_user(req.user_id)
        if not user:
            is_new_user = True
            user = conn.identity.create_user(
                name=req.user_id,
                password=req.password,
                email=req.email,
                domain_id=get_domain_id(conn)
            )

        leader_role = conn.identity.find_role("leader")
        if not leader_role:
            raise HTTPException(status_code=500, detail="leader role이 존재하지 않습니다. CLI로 먼저 생성해주세요.")

        conn.identity.assign_project_role_to_user(
            project=project.id,
            user=user.id,
            role=leader_role.id
        )

        return {
            "status": "success",
            "project_id": project.id,
            "project_name": project.name,
            "user_id": user.id,
            "is_new_user": is_new_user
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ── Form 2: 기존 프로젝트에 유저 추가 ──────────────────────────────

@app.post("/add-user")
def add_user_to_project(req: AddUserRequest):
    conn = get_conn()
    try:
        project = conn.identity.find_project(req.project_name)
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

        is_new_user = False
        user = conn.identity.find_user(req.user_id)
        if not user:
            is_new_user = True
            user = conn.identity.create_user(
                name=req.user_id,
                password=req.password,
                email=req.email,
                domain_id=get_domain_id(conn)
            )

        member_role = conn.identity.find_role("member")
        if not member_role:
            raise HTTPException(status_code=500, detail="member role이 존재하지 않습니다. CLI로 먼저 생성해주세요.")

        conn.identity.assign_project_role_to_user(
            project=project.id,
            user=user.id,
            role=member_role.id
        )

        return {
            "status": "success",
            "project_id": project.id,
            "user_id": user.id,
            "is_new_user": is_new_user
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ── Form 3: 유저 삭제 ──────────────────────────────

@app.delete("/remove-user")
def remove_user_from_project(req: DeleteUserRequest):
    conn = get_conn()
    try:
        project = conn.identity.find_project(req.project_name)
        user = conn.identity.find_user(req.user_id)
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")
        if not user:
            raise HTTPException(status_code=404, detail="유저를 찾을 수 없습니다")

        for role_name in ["member", "leader"]:
            role = conn.identity.find_role(role_name)
            if role:
                try:
                    conn.identity.unassign_project_role_from_user(
                        project=project.id,
                        user=user.id,
                        role=role.id
                    )
                except Exception:
                    pass

        user_projects = list(conn.identity.user_projects(user.id))
        if not user_projects:
            conn.identity.delete_user(user.id)
            return {"status": "success", "user_deleted": True}

        return {"status": "success", "user_deleted": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


# ── Form 4: 프로젝트 삭제 (수동 삭제 + 자동 반납 공용) ──────────────────────────────

@app.delete("/remove-project")
def delete_project(req: DeleteProjectRequest):
    conn = get_conn()
    try:
        project = conn.identity.find_project(req.project_name)
        if not project:
            raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다")

        role_assignments = list(conn.identity.role_assignments(
            scope_project_id=project.id
        ))
        user_ids = list(set([
            a.user["id"] for a in role_assignments if hasattr(a, "user")
        ]))

        servers = list(conn.compute.servers(
            project_id=project.id,
            all_projects=True
        ))
        for server in servers:
            conn.compute.delete_server(server.id)

        for port in conn.network.ports(project_id=project.id):
            try:
                conn.network.delete_port(port.id)
            except Exception:
                pass
        for router in conn.network.routers(project_id=project.id):
            try:
                conn.network.delete_router(router.id)
            except Exception:
                pass
        for network in conn.network.networks(project_id=project.id):
            try:
                conn.network.delete_network(network.id)
            except Exception:
                pass

        conn.identity.delete_project(project.id)

        deleted_users = []
        for uid in user_ids:
            try:
                user_projects = list(conn.identity.user_projects(uid))
                if not user_projects:
                    conn.identity.delete_user(uid)
                    deleted_users.append(uid)
            except Exception:
                pass

        return {
            "status": "success",
            "deleted_users": deleted_users
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))






        ================================
function generatePassword() {
  var chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%";
  var password = "";
  for (var i = 0; i < 12; i++) {
    password += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return password;
}

function sendEmailSafe(to, subject, body) {
  var logSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getSheetByName("이메일로그");
  if (!logSheet) {
    logSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").insertSheet("이메일로그");
  }
  var emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(to)) {
    logSheet.appendRow([new Date(), "정규식불통과", to, subject]);
    return;
  }
  try {
    MailApp.sendEmail(to, subject, body);
    logSheet.appendRow([new Date(), "발송성공", to, subject]);
  } catch (err) {
    logSheet.appendRow([new Date(), "발송실패", to, subject, err.toString()]);
  }
}

// ===== Form 1: 프로젝트 생성 =====
function onSubmit(e) {
  var webhookUrl = "<SLACK_WEBHOOK_URL>";
  var botToken = "<SLACK_BOT_TOKEN>";
  var channelId = "<SLACK_CHANNEL_ID>";
  var responses = e.values;
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastRow = sheet.getLastRow();
  if (sheet.getRange(lastRow, 9).getValue() !== "") return; // 중복 발화 방지

  // 1. 개인정보 미동의
  if (responses[7] === "미동의") {
    sheet.getRange(lastRow, 9).setValue("실패-미동의");
    sendEmailSafe(responses[2], "[HighCloud] 프로젝트 생성 신청 실패", 
      "안녕하세요, " + responses[1] + "님.\n\n프로젝트 생성 신청이 실패하였습니다.\n\n사유: 개인정보 수집·이용 미동의\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌📋 OpenStack 프로젝트 생성 신청 실패*\n*사유:* 개인정보 수집·이용 미동의\n*신청 일시:* " + responses[0] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  // 2. 성함 한글 검증
  if (!/^[가-힣]+$/.test(responses[1])) {
    sheet.getRange(lastRow, 9).setValue("실패-성함오류");
    sendEmailSafe(responses[2], "[HighCloud] 프로젝트 생성 신청 실패",
      "안녕하세요.\n\n프로젝트 생성 신청이 실패하였습니다.\n\n사유: 자음과 모음이 조합된 한글로 입력해주세요.\n입력하신 성함: " + responses[1] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌📋 OpenStack 프로젝트 생성 신청 실패*\n*사유:* 자음과 모음이 조합된 한글이 아닙니다.\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  // 3. 이메일 형식 검증
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(responses[2])) {
    sheet.getRange(lastRow, 9).setValue("실패-이메일오류");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌📋 OpenStack 프로젝트 생성 신청 실패*\n*사유:* 이메일 형식이 올바르지 않습니다.\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  // 4. 프로젝트명 영문 검증 (raw 입력 기준)
  if (!/^[a-zA-Z0-9\-_]+$/.test(responses[3])) {
    sheet.getRange(lastRow, 9).setValue("실패-프로젝트명오류");
    sendEmailSafe(responses[2], "[HighCloud] 프로젝트 생성 신청 실패",
      "안녕하세요, " + responses[1] + "님.\n\n프로젝트 생성 신청이 실패하였습니다.\n\n사유: 프로젝트명은 영문/숫자/하이픈/언더바의 조합만 입력해주세요.\n입력하신 프로젝트명: " + responses[3] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌📋 OpenStack 프로젝트 생성 신청 실패*\n*사유:* 프로젝트명이 영문/숫자/하이픈/언더바의 조합이 아닙니다.\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] + "\n*입력한 프로젝트명:* " + responses[3] })
    });
    return;
  }

  // 5. 대표자 ID 영문+숫자 검증
  if (!/^[a-zA-Z0-9]+$/.test(responses[5])) {
    sheet.getRange(lastRow, 9).setValue("실패-ID오류");
    sendEmailSafe(responses[2], "[HighCloud] 프로젝트 생성 신청 실패",
      "안녕하세요, " + responses[1] + "님.\n\n프로젝트 생성 신청이 실패하였습니다.\n\n사유: 대표자 ID는 영문과 숫자만 입력해주세요.\n입력하신 ID: " + responses[5] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌📋 OpenStack 프로젝트 생성 신청 실패*\n*사유:* 대표자 ID는 영문과 숫자만 입력해야 합니다.\n*입력한 대표자 ID:* " + responses[5]  + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  // 6. 반납일 검증
  var returnDate = new Date(responses[6]);
  var tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  tomorrow.setHours(0, 0, 0, 0);
  returnDate.setHours(0, 0, 0, 0);
  if (returnDate < tomorrow) {
    sheet.getRange(lastRow, 9).setValue("실패-반납일오류");
    sendEmailSafe(responses[2], "[HighCloud] 프로젝트 생성 신청 실패",
      "안녕하세요, " + responses[1] + "님.\n\n프로젝트 생성 신청이 실패하였습니다.\n\n사유: 반납일은 익일부터 선택 가능합니다.\n입력하신 반납일: " + responses[6] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌📋 OpenStack 프로젝트 생성 신청 실패*\n*사유:* 반납일은 익일부터 선택 가능합니다.\n*신청 일시:* " + responses[0] + "\n*대여 기간 (반납일):* " + responses[6] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  // 7. ID+성함+이메일 일치 체크
  var identityCheck = checkUserIdentity(responses[5], responses[1], responses[2]);
  if (identityCheck === "mismatch") {
    sheet.getRange(lastRow, 9).setValue("실패-ID불일치");
    sendEmailSafe(responses[2], "[HighCloud] 프로젝트 생성 신청 실패",
      "안녕하세요, " + responses[1] + "님.\n\n프로젝트 생성 신청이 실패하였습니다.\n\n사유: ID는 존재하지만 성함 또는 이메일이 기존 등록 정보와 일치하지 않습니다.\n대표자 ID: " + responses[5] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌📋 OpenStack 프로젝트 생성 신청 실패*\n*사유:* ID는 존재하지만 성함 또는 이메일이 기존 등록 정보와 일치하지 않습니다\n*대표자 ID:* " + responses[5] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  // 프로젝트 뒤에 날짜 붙이는 로직
  var today = new Date();
  var dateStr = today.getFullYear().toString() +
    String(today.getMonth() + 1).padStart(2, '0') +
    String(today.getDate()).padStart(2, '0');
  var datedProjectName = responses[3] + "-" + dateStr;
  sheet.getRange(lastRow, 4).setValue(datedProjectName);

  // 8. 프로젝트명(날짜 포함) 중복 체크
  var conflict = checkProjectNameConflict(datedProjectName);
  if (conflict.state !== "none") {
    var sameLeader = (String(conflict.leader) === String(responses[5]));
    var statusVal, emailSubject, emailBody, slackText;

    if (sameLeader && conflict.state === "pending") {
      statusVal = "안내-이미대기중";
      emailSubject = "[HighCloud] 프로젝트 생성 신청 안내";
      emailBody = "안녕하세요, " + responses[1] + "님.\n\n동일 프로젝트명(" + datedProjectName + ")으로 이미 신청하셨고 승인 대기 중입니다.\n잠시만 기다려주세요.\n\n감사합니다.";
      slackText = "*📋 프로젝트 생성 신청 — 중복*\n*사유:* 동일 프로젝트명으로 이미 신청되어 승인 대기 중입니다\n*프로젝트명:* " + datedProjectName + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2];
    } else if (sameLeader && conflict.state === "active") {
      statusVal = "안내-이미운영중";
      emailSubject = "[HighCloud] 프로젝트 생성 신청 안내";
      emailBody = "안녕하세요, " + responses[1] + "님.\n\n이미 생성되어 운영 중인 프로젝트(" + datedProjectName + ")입니다.\n\n감사합니다.";
      slackText = "*📋 프로젝트 생성 신청 — 중복*\n*사유:* 이미 생성되어 운영 중인 프로젝트입니다\n*프로젝트명:* " + datedProjectName + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2];
    } else {
      statusVal = "실패-중복프로젝트명";
      emailSubject = "[HighCloud] 프로젝트 생성 신청 실패";
      emailBody = "안녕하세요, " + responses[1] + "님.\n\n프로젝트 생성 신청이 실패하였습니다.\n\n사유: 이미 존재하는 프로젝트명입니다.\n입력하신 프로젝트명: " + datedProjectName + "\n\n감사합니다.";
      slackText = "*❌📋 프로젝트 생성 신청 실패*\n*사유:* 이미 존재하는 프로젝트명입니다\n*프로젝트명:* " + datedProjectName + "\n*대표자 ID:* " + responses[5] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2];
    }

    sheet.getRange(lastRow, 9).setValue(statusVal);
    sendEmailSafe(responses[2], emailSubject, emailBody);
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": slackText })
    });
    return;
  }

  sheet.getRange(lastRow, 9).setValue("대기중");

  var blocks = [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*📋 OpenStack 프로젝트 생성 신청*\n*신청 일시:* " + responses[0] + "\n\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] + "\n*프로젝트명:* " + datedProjectName + "\n*사용 목적:* " + responses[4] + "\n*대표자 ID:* " + responses[5] + "\n*대여 기간 (반납일):* " + responses[6]
      }
    },
    {
      "type": "actions",
      "elements": [
        { "type": "button", "text": { "type": "plain_text", "text": "✅ 승인" }, "style": "primary", "action_id": "approve", "value": JSON.stringify({ "row": lastRow, "type": "create" }) },
        { "type": "button", "text": { "type": "plain_text", "text": "❌ 거절" }, "style": "danger", "action_id": "reject", "value": JSON.stringify({ "row": lastRow, "type": "create" }) }
      ]
    }
  ];

  UrlFetchApp.fetch("https://slack.com/api/chat.postMessage", {
    "method": "post", "contentType": "application/json",
    "headers": { "Authorization": "Bearer " + botToken },
    "payload": JSON.stringify({ "channel": channelId, "blocks": blocks })
  });
}

// 같은 프로젝트명이 대기중 or 승인+미반납으로 있나 검사
function checkProjectNameConflict(projectName) {
  var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
  var data = createSheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (data[i][3] !== projectName) continue;
    var approval = data[i][8];
    var returned = data[i][9];
    var leader = String(data[i][5]);
    if (approval === "대기중") return { state: "pending", leader: leader };
    if (approval === "승인" && returned === "미반납") return { state: "active", leader: leader };
  }
  return { state: "none", leader: null };
}

// 이미 있는 신청자의 개인정보가 신청의 개인정보와 일치한지 확인
function checkUserIdentity(userId, name, email) {
  var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
  var addSheet = SpreadsheetApp.openById("<ADD_SHEET_ID>").getActiveSheet();
  var createData = createSheet.getDataRange().getValues();
  var addData = addSheet.getDataRange().getValues();

  for (var i = 1; i < createData.length; i++) {
    if (String(createData[i][5]) === String(userId) && createData[i][8] === "승인") {
      if (createData[i][1] !== name || createData[i][2] !== email) return "mismatch";
    }
  }
  for (var i = 1; i < addData.length; i++) {
    if (String(addData[i][4]) === String(userId) && addData[i][6] === "승인") {
      if (addData[i][1] !== name || addData[i][2] !== email) return "mismatch";
    }
  }
  return "ok";
}

function doPost(e) {
  Logger.log("doPost 시작");
  Logger.log(JSON.stringify(e.parameter));

  var action = JSON.parse(e.parameter.payload);
  var actionId = action.actions[0].action_id;
  var value = JSON.parse(action.actions[0].value);
  var row = value.row;
  var type = value.type;
  var channel = action.channel.id;
  var ts = action.message.ts;
  var originalText = action.message.blocks[0].text.text;
  var botToken = "<SLACK_BOT_TOKEN>";
  var fastapiUrl = "<FASTAPI_URL>";

  var sheetId, approvalCol;
  if (type === "create") {
    sheetId = "<CREATE_SHEET_ID>";
    approvalCol = 9;
  } else if (type === "add_user") {
    sheetId = "<ADD_SHEET_ID>";
    approvalCol = 7;
  } else if (type === "delete_user") {
    sheetId = "<DELETE_USER_SHEET_ID>";
    approvalCol = 7;
  } else if (type === "delete_project") {
    sheetId = "<DELETE_PROJECT_SHEET_ID>";
    approvalCol = 8;
  }

  var sheet = SpreadsheetApp.openById(sheetId).getActiveSheet();
  var statusText, statusStyle;

  if (actionId === "approve") {
    var apiResult = callFastAPI(fastapiUrl, type, sheet, row);
    Logger.log("apiResult: " + JSON.stringify(apiResult));

    if (apiResult.success) {
      sheet.getRange(row, approvalCol).setValue("승인");
      statusText = "승인 완료";
      statusStyle = "primary";

      var recipientEmail = String(sheet.getRange(row, 3).getValue());
      var recipientName = String(sheet.getRange(row, 2).getValue());
      var userId = String(sheet.getRange(row, type === "create" ? 6 : 5).getValue());
      var projectName = type === "create" ? apiResult.data.project_name : String(sheet.getRange(row, 4).getValue());
      var initialPassword = apiResult.password;

      var nameNotice = "\n\n※ 유저 추가/삭제·프로젝트 삭제 신청 시에는 프로젝트명을 위 이름(" + projectName + ") 그대로 입력해주세요.";

      if (type === "create") {
        sheet.getRange(row, 10).setValue("미반납");
        sheet.getRange(row, 11).setValue("재직중");
        if (apiResult.data.is_new_user) {
            sendEmailSafe(recipientEmail, "[HighCloud] 프로젝트 생성 승인 및 초기 비밀번호 안내",
              "안녕하세요, " + recipientName + "님.\n\n프로젝트 생성이 승인되었습니다.\n\n" +
              "프로젝트명: " + projectName + "\n" +
              "아이디: " + userId + "@highcloud" + "\n" +
              "초기 비밀번호: " + initialPassword + "\n\n" +
              "보안을 위해 로그인 후 반드시 비밀번호를 변경해주세요." + nameNotice + "\n\n감사합니다.");
        } else {
            sendEmailSafe(recipientEmail, "[HighCloud] 프로젝트 생성 승인 안내",
              "안녕하세요, " + recipientName + "님.\n\n프로젝트 생성이 승인되었습니다.\n\n" +
              "프로젝트명: " + projectName + "\n" +
              "아이디: " + userId + "\n\n" +
              "기존 비밀번호로 로그인하시면 됩니다." + nameNotice + "\n\n감사합니다.");
        }
    } else if (type === "add_user") {
        sheet.getRange(row, 8).setValue("미반납");
        sheet.getRange(row, 9).setValue("재직중");
        if (apiResult.data.is_new_user) {
            sendEmailSafe(recipientEmail, "[HighCloud] 유저 추가 승인 및 초기 비밀번호 안내",
              "안녕하세요, " + recipientName + "님.\n\n프로젝트에 유저 추가가 승인되었습니다.\n\n" +
              "프로젝트명: " + projectName + "\n" +
              "아이디: " + userId + "\n" +
              "초기 비밀번호: " + initialPassword + "\n\n" +
              "보안을 위해 로그인 후 반드시 비밀번호를 변경해주세요.\n\n감사합니다.");
        } else {
            sendEmailSafe(recipientEmail, "[HighCloud] 유저 추가 승인 안내",
              "안녕하세요, " + recipientName + "님.\n\n프로젝트에 유저 추가가 승인되었습니다.\n\n" +
              "프로젝트명: " + projectName + "\n" +
              "아이디: " + userId + "\n\n" +
              "기존 비밀번호로 로그인하시면 됩니다.\n\n감사합니다.");
        }
    }

      if (type === "delete_user") {
        var deleteEmail = String(sheet.getRange(row, 3).getValue());
        var deleteName = String(sheet.getRange(row, 2).getValue());
        var deleteProjectName = String(sheet.getRange(row, 4).getValue());
        var deleteUserId = String(sheet.getRange(row, 5).getValue());

        sendEmailSafe(deleteEmail, "[HighCloud] 유저 삭제 완료 안내",
          "안녕하세요, " + deleteName + "님.\n\n" +
          "프로젝트 [" + deleteProjectName + "]에서 유저 [" + deleteUserId + "] 삭제가 완료되었습니다.\n\n감사합니다.");

        var addSheet = SpreadsheetApp.openById("<ADD_SHEET_ID>").getActiveSheet();
        var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
        var addData = addSheet.getDataRange().getValues();
        var createData = createSheet.getDataRange().getValues();

        for (var i = 1; i < addData.length; i++) {
          if (addData[i][3] === deleteProjectName && String(addData[i][4]) === deleteUserId && addData[i][6] === "승인") {
            addSheet.getRange(i + 1, 9).setValue("탈퇴");
          }
        }
        for (var i = 1; i < createData.length; i++) {
          if (createData[i][3] === deleteProjectName && String(createData[i][5]) === deleteUserId && createData[i][8] === "승인") {
            createSheet.getRange(i + 1, 11).setValue("탈퇴");
          }
        }
      }

      if (type === "delete_project") {
        var delProjectName = String(sheet.getRange(row, 4).getValue());
        var delLeaderEmail = String(sheet.getRange(row, 3).getValue());
        var delLeaderName = String(sheet.getRange(row, 2).getValue());

        sendEmailSafe(delLeaderEmail, "[HighCloud] 프로젝트 삭제 완료 안내",
          "안녕하세요, " + delLeaderName + "님.\n\n" +
          "프로젝트 [" + delProjectName + "] 삭제가 완료되었습니다.\n\n감사합니다.");

        var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
        var addSheet = SpreadsheetApp.openById("<ADD_SHEET_ID>").getActiveSheet();
        var createData = createSheet.getDataRange().getValues();
        var addData = addSheet.getDataRange().getValues();
        var affectedUsers = [];

        for (var i = 1; i < createData.length; i++) {
          if (createData[i][3] === delProjectName && createData[i][8] === "승인" && createData[i][9] === "미반납") {
            createSheet.getRange(i + 1, 10).setValue("반납완료");
            createSheet.getRange(i + 1, 11).setValue("탈퇴");
            affectedUsers.push(String(createData[i][5]));
          }
        }
        for (var i = 1; i < addData.length; i++) {
          if (addData[i][3] === delProjectName && addData[i][6] === "승인" && addData[i][7] === "미반납") {
            addSheet.getRange(i + 1, 8).setValue("반납완료");
            addSheet.getRange(i + 1, 9).setValue("탈퇴");
            affectedUsers.push(String(addData[i][4]));
          }
        }

        createData = createSheet.getDataRange().getValues();
        addData = addSheet.getDataRange().getValues();
        var seen = {};
        for (var u = 0; u < affectedUsers.length; u++) {
          var uid = affectedUsers[u];
          if (seen[uid]) continue;
          seen[uid] = true;
          var hasActive = false;
          for (var i = 1; i < createData.length; i++) {
            if (String(createData[i][5]) === uid && createData[i][8] === "승인" && createData[i][9] === "미반납") {
              hasActive = true; break;
            }
          }
          if (!hasActive) {
            for (var i = 1; i < addData.length; i++) {
              if (String(addData[i][4]) === uid && addData[i][6] === "승인" && addData[i][7] === "미반납") {
                hasActive = true; break;
              }
            }
          }
          if (!hasActive) {
            for (var i = 1; i < createData.length; i++) {
              if (String(createData[i][5]) === uid) createSheet.getRange(i + 1, 11).setValue("탈퇴");
            }
            for (var i = 1; i < addData.length; i++) {
              if (String(addData[i][4]) === uid) addSheet.getRange(i + 1, 9).setValue("탈퇴");
            }
          }
        }
      }

    } else {
      sheet.getRange(row, approvalCol).setValue("실패-OpenStack오류");
      statusText = "오류 발생";
      statusStyle = "danger";

      var failEmail = String(sheet.getRange(row, 3).getValue());
      var failName = String(sheet.getRange(row, 2).getValue());
      var failDetail = apiResult.data ? String(apiResult.data.detail) : "알 수 없는 오류";
      sendEmailSafe(failEmail, "[HighCloud] 신청 처리 실패 안내",
        "안녕하세요, " + failName + "님.\n\n신청 처리 중 오류가 발생하였습니다.\n\n사유: " + failDetail + "\n\n다시 신청해주세요.\n\n감사합니다.");
    }

  } else if (actionId === "reject") {
    sheet.getRange(row, approvalCol).setValue("거절");
    statusText = "거절 완료";
    statusStyle = "danger";

    var rejectEmail = String(sheet.getRange(row, 3).getValue());
    var rejectName = String(sheet.getRange(row, 2).getValue());
    var rejectProject = String(sheet.getRange(row, 4).getValue());
    var subjectMap = {
      "create": "프로젝트 생성 신청 거절",
      "add_user": "유저 추가 신청 거절",
      "delete_user": "유저 삭제 신청 거절",
      "delete_project": "프로젝트 삭제 신청 거절"
    };
    sendEmailSafe(rejectEmail, "[HighCloud] " + (subjectMap[type] || "신청 거절"),
      "안녕하세요, " + rejectName + "님.\n\n" +
      "[" + rejectProject + "] " + (subjectMap[type] || "신청") + " 안내드립니다.\n\n" +
      "관리자에 의해 거절되었습니다. 자세한 사유는 관리자에게 문의해주세요.\n\n감사합니다.");

  } else {
    return ContentService.createTextOutput("ok");
  }

  UrlFetchApp.fetch("https://slack.com/api/chat.update", {
    "method": "post", "contentType": "application/json",
    "headers": { "Authorization": "Bearer " + botToken },
    "payload": JSON.stringify({
      "channel": channel, "ts": ts,
      "blocks": [
        { "type": "section", "text": { "type": "mrkdwn", "text": originalText } },
        { "type": "actions", "elements": [
          { "type": "button", "text": { "type": "plain_text", "text": statusText }, "style": statusStyle, "action_id": "done", "value": "done" }
        ]}
      ]
    })
  });

  return ContentService.createTextOutput("ok");
}

function callFastAPI(baseUrl, type, sheet, row) {
  try {
    var url, method, payload;
    var password = generatePassword();
    var projName = String(sheet.getRange(row, 4).getValue());

    if (type === "create") {
      url = baseUrl + "/create";
      method = "post";
      payload = {
        "project_name": projName,
        "user_id": String(sheet.getRange(row, 6).getValue()),
        "email": String(sheet.getRange(row, 3).getValue()),
        "password": password
      };
      Logger.log("payload: " + JSON.stringify(payload));
    } else if (type === "add_user") {
      url = baseUrl + "/add-user";
      method = "post";
      payload = {
        "project_name": projName,
        "user_id": String(sheet.getRange(row, 5).getValue()),
        "email": String(sheet.getRange(row, 3).getValue()),
        "password": password
      };
    } else if (type === "delete_user") {
      url = baseUrl + "/remove-user";
      method = "delete";
      payload = {
        "project_name": projName,
        "user_id": String(sheet.getRange(row, 5).getValue())
      };
    } else if (type === "delete_project") {
      url = baseUrl + "/remove-project";
      method = "delete";
      payload = {
        "project_name": projName
      };
    }

    var response = UrlFetchApp.fetch(url, {
      "method": method,
      "contentType": "application/json",
      "payload": JSON.stringify(payload),
      "muteHttpExceptions": true
    });

    Logger.log("FastAPI 응답: " + response.getContentText());
    var result = JSON.parse(response.getContentText());
    return { "success": result.status === "success", "data": result, "password": password };

  } catch (err) {
    Logger.log("FastAPI 오류: " + err.toString());
    return { "success": false, "error": err.toString() };
  }
}