// 부모만족도 조사 — 응답지 PDF를 어린이집 이메일로 보내는 부분
// ------------------------------------------------------------------
// 브라우저가 /api/send 로 { to, org, ..., pdfBase64 } 를 보내면
// 환경변수에 넣어둔 열쇠(BREVO_API_KEY)로 메일을 보냅니다.
//
// ★ 메일 설정을 하지 않아도 앱은 그대로 동작합니다.
//   설정이 없으면 부모님 화면에서 "PDF를 저장해서 직접 보내주세요"로 안내됩니다.

module.exports = async (req, res) => {
  if (req.method !== "POST") { res.status(405).json({ error: "POST만 허용됩니다." }); return; }

  const KEY = process.env.BREVO_API_KEY;                       // Brevo API 키
  const FROM = process.env.FROM_EMAIL;                         // 인증된 발신 이메일
  const FROMNAME = process.env.FROM_NAME || "부모만족도 조사";

  if (!KEY || !FROM) {
    res.status(500).json({ error: "메일 자동 발송이 아직 설정되지 않았습니다. (BREVO_API_KEY / FROM_EMAIL)" });
    return;
  }

  try {
    const b = typeof req.body === "string" ? JSON.parse(req.body) : (req.body || {});
    const { to, org, year, role, age, filename, pdfBase64 } = b;

    if (!to || !pdfBase64) { res.status(400).json({ error: "받는 이메일 또는 응답지가 없습니다." }); return; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(to)) { res.status(400).json({ error: "받는 이메일 형식이 올바르지 않습니다." }); return; }
    if (pdfBase64.length > 8 * 1024 * 1024) { res.status(413).json({ error: "첨부 파일이 너무 큽니다." }); return; }

    const subject = `[부모만족도 조사] ${org || ""} 응답지 1건 도착`;
    const text =
      `${org || ""} 부모만족도 조사 응답지가 도착했습니다.\n\n` +
      `· 어린이집: ${org || "-"}\n` +
      `· 조사 연도: ${year || "-"}\n` +
      `· 참여자: ${role || "-"}\n` +
      `· 자녀 연령: ${age || "-"}\n\n` +
      `첨부된 PDF를 내려받아 두었다가, 결과 화면에 한꺼번에 올리시면\n` +
      `평균 점수와 그래프가 자동으로 집계됩니다.\n\n` +
      `(이 응답은 무기명입니다.)`;

    const payload = {
      sender: { name: FROMNAME, email: FROM },
      to: [{ email: to }],
      subject,
      textContent: text,
      attachment: [{ content: pdfBase64, name: filename || "부모만족도_응답지.pdf" }]
    };

    const r = await fetch("https://api.brevo.com/v3/smtp/email", {
      method: "POST",
      headers: { "api-key": KEY, "Content-Type": "application/json", "accept": "application/json" },
      body: JSON.stringify(payload)
    });

    if (r.status >= 200 && r.status < 300) {
      res.status(200).json({ ok: true });
    } else {
      const t = await r.text();
      res.status(502).json({ error: "메일 전송 실패: " + t.slice(0, 300) });
    }
  } catch (e) {
    res.status(500).json({ error: String((e && e.message) || e) });
  }
};
