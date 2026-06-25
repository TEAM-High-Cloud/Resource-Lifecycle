function onSubmit(e) {
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
        sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 추가 신청이 실패하였습니다.\n\n사유: 개인정보 수집·이용 미동의\n\n감사합니다.");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 개인정보 수집·이용 미동의\n*신청 일시:* " + responses[0] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 2. 성함 한글 검증
    if (!/^[가-힣]+$/.test(responses[1])) {
        sheet.getRange(lastRow, 7).setValue("실패-성함오류");
        sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요.\n\n유저 추가 신청이 실패하였습니다.\n\n사유: 성함은 자음과 모음이 조합된 한글로 입력해주세요.\n입력하신 성함: " + responses[1] + "\n\n감사합니다.");
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
        sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 추가 신청이 실패하였습니다.\n\n사유: 추가할 유저 ID는 영문과 숫자만 입력해주세요.\n입력하신 유저 ID: " + responses[4] + "\n\n감사합니다.");
    
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
        sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 추가 신청이 실패하였습니다.\n\n사유: 프로젝트가 아직 승인 대기중입니다.\n프로젝트명: " + responses[3] + "\n\n감사합니다.");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 프로젝트 승인 대기중입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 6. 존재하지 않는 프로젝트에 유저 추가 신청했을 때
    if (projectStatus === "없음") {
        sheet.getRange(lastRow, 7).setValue("실패-없는프로젝트");
        sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 추가 신청이 실패하였습니다.\n\n사유: 존재하지 않는 프로젝트입니다.\n프로젝트명: " + responses[3] + "\n(프로젝트명은 승인 메일에 안내된 날짜 포함 이름으로 입력해주세요.)\n\n감사합니다.");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 없는 프로젝트입니다\n*프로젝트명:* " + responses[3] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 7. 중복 ID 체크
    if (isDuplicateUserId(responses[3], responses[4])) {
        sheet.getRange(lastRow, 7).setValue("실패-중복ID");
        sendEmailSafe(responses[2], FAIL_SUBJECT,
      "안녕하세요, " + responses[1] + "님.\n\n유저 추가 신청이 실패하였습니다.\n\n사유: 해당 프로젝트에 이미 존재하는 유저 ID입니다.\n프로젝트명: " + responses[3] + "\n유저 ID: " + responses[4] + "\n\n감사합니다.");
        UrlFetchApp.fetch(webhookUrl, {
        "method": "post", "contentType": "application/json",
        "payload": JSON.stringify({ "text": "*❌ 유저 추가 신청 실패*\n*사유:* 해당 프로젝트에 이미 존재하는 ID\n*프로젝트명:* " + responses[3] + "\n*추가할 유저 ID:* " + responses[4] + "\n*성함:* " + responses[1] + "\n*이메일:* " + responses[2] })
        });
        return;
    }

    // 8. 정상 신청
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

// 거절/반납완료에서 조기반환하지 않고, 살아있는(승인+미반납)을 끝까지 탐색
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


function isDuplicateUserId(projectName, newUserId) {
    var createSheet = SpreadsheetApp.openById("<CREATE_SHEET_ID>").getActiveSheet();
    var addSheet = SpreadsheetApp.openById("<ADD_SHEET_ID>").getActiveSheet();
    var createData = createSheet.getDataRange().getValues();
    var addData = addSheet.getDataRange().getValues();

    for (var i = 1; i < createData.length; i++) {
        if (createData[i][3] === projectName &&
            String(createData[i][5]) === String(newUserId) &&
            createData[i][8] === "승인" &&
            createData[i][9] === "미반납" &&
            createData[i][10] !== "탈퇴") return true;
    }
    for (var i = 1; i < addData.length; i++) {
        if (addData[i][3] === projectName &&
            String(addData[i][4]) === String(newUserId) &&
            addData[i][6] === "승인" &&
            addData[i][7] === "미반납" &&
            addData[i][8] !== "탈퇴") return true;
    }
    return false;
}