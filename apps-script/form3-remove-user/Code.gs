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

// 비밀번호 검증: FastAPI /verify-password 호출 → 맞으면 true
function verifyPasswordViaAPI(fastapiUrl, userId, password) {
  try {
    var response = UrlFetchApp.fetch(fastapiUrl + "/verify-password", {
      "method": "post",
      "contentType": "application/json",
      "payload": JSON.stringify({ "user_id": userId, "password": password }),
      "muteHttpExceptions": true
    });
    var result = JSON.parse(response.getContentText());
    return result.status === "success" && result.valid === true;
  } catch (err) {
    return false; // 통신 실패 시 삭제 차단 (fail-safe)
  }
}

function onSubmit(e) {
  var webhookUrl = "<SLACK_WEBHOOK_URL>";
  var botToken = "<SLACK_BOT_TOKEN>";
  var channelId = "<SLACK_CHANNEL_ID>";
  var fastapiUrl = "<FASTAPI_URL>";
  var responses = e.values;
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastRow = sheet.getLastRow();
  if (sheet.getRange(lastRow, 7).getValue() !== "") return;
  var FAIL_SUBJECT = "[HighCloud] 유저 삭제 신청 실패";

  var inputPassword = responses[5];

  var projectStatus = getProjectStatus(responses[3]);
  if (projectStatus === "대기중") {
    sheet.getRange(lastRow, 7).setValue("실패-프로젝트대기중");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 삭제 신청이 실패하였습니다.\n\n사유: 프로젝트가 아직 승인 대기중입니다.\n프로젝트명: " + responses[3] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 유저 삭제 신청 실패*\n*사유:* 프로젝트 승인 대기중입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }
  if (projectStatus === "없음") {
    sheet.getRange(lastRow, 7).setValue("실패-없는프로젝트");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 삭제 신청이 실패하였습니다.\n\n사유: 존재하지 않는 프로젝트입니다.\n프로젝트명: " + responses[3] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 유저 삭제 신청 실패*\n*사유:* 없는 프로젝트입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  var deleteCheck = checkDeleteUserIdentity(responses[3], responses[4], responses[1], responses[2]);
  if (deleteCheck === "not_found") {
    sheet.getRange(lastRow, 7).setValue("실패-없는ID");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 삭제 신청이 실패하였습니다.\n\n사유: 해당 프로젝트에 존재하지 않는 유저 ID입니다.\n프로젝트명: " + responses[3] + "\n유저 ID: " + responses[4] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 유저 삭제 신청 실패*\n*사유:* 해당 프로젝트에 존재하지 않는 ID입니다\n*프로젝트명:* " + responses[3] + "\n*삭제할 유저 ID:* " + responses[4] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }
  if (deleteCheck === "mismatch") {
    sheet.getRange(lastRow, 7).setValue("실패-정보불일치");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 삭제 신청이 실패하였습니다.\n\n사유: 유저 ID는 존재하지만 성함 또는 이메일이 등록 정보와 일치하지 않습니다.\n프로젝트명: " + responses[3] + "\n유저 ID: " + responses[4] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 유저 삭제 신청 실패*\n*사유:* ID는 존재하지만 성함 또는 이메일이 등록 정보와 일치하지 않습니다\n*프로젝트명:* " + responses[3] + "\n*삭제할 유저 ID:* " + responses[4] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  if (isProjectLeader(responses[3], responses[4])) {
    sheet.getRange(lastRow, 7).setValue("실패-리더삭제불가");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 삭제 신청이 실패하였습니다.\n\n사유: 프로젝트 대표자는 유저 삭제로 탈퇴할 수 없습니다. 프로젝트 삭제 신청을 이용해주세요.\n프로젝트명: " + responses[3] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 유저 삭제 신청 실패*\n*사유:* 프로젝트 대표자는 유저 삭제로 탈퇴할 수 없습니다. 프로젝트 삭제 신청을 이용해주세요.\n*프로젝트명:* " + responses[3] + "\n*대표자 ID:* " + responses[4] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  if (!verifyPasswordViaAPI(fastapiUrl, responses[4], inputPassword)) {
    sheet.getRange(lastRow, 7).setValue("실패-비번불일치");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 삭제 신청이 실패하였습니다.\n\n사유: 비밀번호가 일치하지 않습니다.\n프로젝트명: " + responses[3] + "\n유저 ID: " + responses[4] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 유저 삭제 신청 실패*\n*사유:* 비밀번호가 일치하지 않습니다\n*프로젝트명:* " + responses[3] + "\n*삭제할 유저 ID:* " + responses[4] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  sheet.getRange(lastRow, 7).setValue("대기중");

  var blocks = [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*🗑️ 유저 삭제 신청*\n*신청 일시:* " + responses[0] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] + "\n*대상 프로젝트명:* " + responses[3] + "\n*삭제할 유저 ID:* " + responses[4]
      }
    },
    {
      "type": "actions",
      "elements": [
        { "type": "button", "text": { "type": "plain_text", "text": "✅ 승인" }, "style": "primary", "action_id": "approve", "value": JSON.stringify({ "row": lastRow, "type": "delete_user" }) },
        { "type": "button", "text": { "type": "plain_text", "text": "❌ 거절" }, "style": "danger", "action_id": "reject", "value": JSON.stringify({ "row": lastRow, "type": "delete_user" }) }
      ]
    }
  ];

  UrlFetchApp.fetch("https://slack.com/api/chat.postMessage", {
    "method": "post", "contentType": "application/json",
    "headers": { "Authorization": "Bearer " + botToken },
    "payload": JSON.stringify({ "channel": channelId, "blocks": blocks })
  });
}

function getProjectStatus(projectName) {
  var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
  var data = createSheet.getDataRange().getValues();
  var hasPending = false;
  for (var i = 1; i < data.length; i++) {
    if (data[i][3] !== projectName) continue;
    var approval = data[i][8];
    var returned = data[i][9];
    if (approval === "승인" && returned === "미반납") return "승인";
    if (approval === "대기중") hasPending = true;
  }
  if (hasPending) return "대기중";
  return "없음";
}

function checkDeleteUserIdentity(projectName, userId, name, email) {
  var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
  var addSheet = SpreadsheetApp.openById("<ADD_SHEET_ID>").getActiveSheet();
  var createData = createSheet.getDataRange().getValues();
  var addData = addSheet.getDataRange().getValues();

  for (var i = 1; i < createData.length; i++) {
    if (createData[i][3] === projectName &&
        String(createData[i][5]) === String(userId) &&
        createData[i][8] === "승인" &&
        createData[i][9] === "미반납" &&
        createData[i][10] !== "탈퇴") {
      if (createData[i][1] !== name || createData[i][2] !== email) return "mismatch";
      return "ok";
    }
  }
  for (var i = 1; i < addData.length; i++) {
    if (addData[i][3] === projectName &&
        String(addData[i][4]) === String(userId) &&
        addData[i][6] === "승인" &&
        addData[i][7] === "미반납" &&
        addData[i][8] !== "탈퇴") {
      if (addData[i][1] !== name || addData[i][2] !== email) return "mismatch";
      return "ok";
    }
  }
  return "not_found";
}

function isProjectLeader(projectName, userId) {
  var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
  var data = createSheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (data[i][3] === projectName &&
        String(data[i][5]) === String(userId) &&
        data[i][8] === "승인" &&
        data[i][9] === "미반납") {
      return true;
    }
  }
  return false;
}