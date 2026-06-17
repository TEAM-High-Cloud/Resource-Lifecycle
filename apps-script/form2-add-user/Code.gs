function onSubmit(e) {
    .
    var webhookUrl = "<SLACK_WEBHOOK_URL>";
    var botToken = "<SLACK_BOT_TOKEN>";
    var channelId = "<SLACK_CHANNEL_ID>";
    var responses = e.values;
    var sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
    var lastRow = sheet.getLastRow();

    
    if (sheet.getRange(lastRow, 7).getValue() !== "") return;
    var FAIL_SUBJECT = "[HighCloud] 유저 추가 신청 실패";

    // 1. 개인정보 미동의
    if (responses[5] === "미동의") {
        sheet.getRange(lastRow, 7).setValue("실패-미동의");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 개인정보 수집·이용 미동의\n*신청 일시:* " + responses[0] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 2. 성함 한글 검증
    if (!/^[가-힣]+$/.test(responses[1])) {
        sheet.getRange(lastRow, 7).setValue("실패-성함오류");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 자음과 모음이 조합된 한글이 아닙니다.\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 3. 이메일 형식 검증
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(responses[2])) {
        sheet.getRange(lastRow, 7).setValue("실패-이메일오류");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 이메일 형식이 올바르지 않습니다.\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 4. 추가할 유저 ID 영문+숫자 검증
    if (!/^[a-zA-Z0-9]+$/.test(responses[4])) {
        sheet.getRange(lastRow, 7).setValue("실패-ID오류");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 추가할 유저 ID는 영문과 숫자만 입력해주세요\n*추가할 유저 ID:* " + responses[4] })
        });
        return;
    }

    // 5. 프로젝트 상태 체크 (responses[3] = 날짜 포함 전체 이름)
    var projectStatus = getProjectStatus(responses[3]);
    if (projectStatus === "대기중") {
        sheet.getRange(lastRow, 7).setValue("실패-프로젝트대기중");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 프로젝트 승인 대기중입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 6. 존재하지 않는 프로젝트에 유저 추가 신청했을 때
    if (projectStatus === "없음") {
        sheet.getRange(lastRow, 7).setValue("실패-없는프로젝트");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 없는 프로젝트입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }



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

