function onSubmit(e) {
  var webhookUrl = "<SLACK_WEBHOOK_URL>";
  var botToken = "<SLACK_BOT_TOKEN>";
  var channelId = "<SLACK_CHANNEL_ID>";
  var responses = e.values;
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  var lastRow = sheet.getLastRow();
  if (sheet.getRange(lastRow, 7).getValue() !== "") return;
  var FAIL_SUBJECT = "[HighCloud] 유저 추가 신청 실패";


  sheet.getRange(lastRow, 7).setValue("대기중");
  sheet.getRange(lastRow, 8).setValue("미반납");
  sheet.getRange(lastRow, 9).setValue("재직중");

  var blocks = [
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*😊 유저 추가 신청*\n*신청 일시:* " + responses[0] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] + "\n*프로젝트명:* " + responses[3] + "\n*추가할 유저 ID:* " + responses[4]
      }
    },
    {
      "type": "actions",
      "elements": [
        { "type": "button", "text": { "type": "plain_text", "text": "✅ 승인" }, "style": "primary", "action_id": "approve", "value": JSON.stringify({ "row": lastRow, "type": "add_user" }) },
        { "type": "button", "text": { "type": "plain_text", "text": "❌ 거절" }, "style": "danger", "action_id": "reject", "value": JSON.stringify({ "row": lastRow, "type": "add_user" }) }
      ]
    }
  ];

  UrlFetchApp.fetch("https://slack.com/api/chat.postMessage", {
    "method": "post", "contentType": "application/json",
    "headers": { "Authorization": "Bearer " + botToken },
    "payload": JSON.stringify({ "channel": channelId, "blocks": blocks })
  });
}

