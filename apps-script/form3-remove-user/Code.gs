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
  if (sheet.getRange(lastRow, 7).getValue() !== "") return;

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