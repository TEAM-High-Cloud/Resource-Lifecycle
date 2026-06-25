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

function onSubmit(e) {
  var webhookUrl = "<SLACK_WEBHOOK_URL>";
  var botToken = "<SLACK_BOT_TOKEN>";
  var channelId = "<SLACK_CHANNEL_ID>";
  var responses = e.values;
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastRow = sheet.getLastRow();
  if (sheet.getRange(lastRow, 8).getValue() !== "") return;
  var FAIL_SUBJECT = "[HighCloud] 프로젝트 삭제 신청 실패";

  // 마지막 확인 "아니오" → 취소 (실패 아님, 메일 미발송)
  if (responses[5] === "아니오") {
    sheet.getRange(lastRow, 8).setValue("취소");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*✂️ 유저가 프로젝트 삭제 신청을 하려다가 말았습니다*\n*신청 일시:* " + responses[0] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  var projectStatus = getProjectStatus(responses[3]);
  if (projectStatus === "대기중") {
    sheet.getRange(lastRow, 8).setValue("실패-프로젝트대기중");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n프로젝트 삭제 신청이 실패하였습니다.\n\n사유: 프로젝트가 아직 승인 대기중입니다.\n프로젝트명: " + responses[3] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 프로젝트 삭제 신청 실패*\n*사유:* 프로젝트 승인 대기중입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }
  if (projectStatus === "없음") {
    sheet.getRange(lastRow, 8).setValue("실패-없는프로젝트");
    sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n프로젝트 삭제 신청이 실패하였습니다.\n\n사유: 존재하지 않는 프로젝트입니다.\n프로젝트명: " + responses[3] + "\n\n감사합니다.");
    UrlFetchApp.fetch(webhookUrl, {
      "method": "post", "contentType": "application/json",
      "payload": JSON.stringify({ "text": "*❌ 프로젝트 삭제 신청 실패*\n*사유:* 없는 프로젝트입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
    });
    return;
  }

  sheet.getRange(lastRow, 8).setValue("대기중");

  var blocks = [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*🗑️ 프로젝트 삭제 신청*\n*신청 일시:* " + responses[0] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] + "\n*삭제할 프로젝트명:* " + responses[3] + "\n*대표자 ID:* " + responses[4]
      }
    },
    {
      "type": "actions",
      "elements": [
        { "type": "button", "text": { "type": "plain_text", "text": "✅ 승인" }, "style": "primary", "action_id": "approve", "value": JSON.stringify({ "row": lastRow, "type": "delete_project" }) },
        { "type": "button", "text": { "type": "plain_text", "text": "❌ 거절" }, "style": "danger", "action_id": "reject", "value": JSON.stringify({ "row": lastRow, "type": "delete_project" }) }
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