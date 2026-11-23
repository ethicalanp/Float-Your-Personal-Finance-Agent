import { NextRequest, NextResponse } from "next/server";

// Fallback rule analyzer matching apps/api/app/services/scam_detector.py
function analyzeFallback(message: string) {
  const lower = message.toLowerCase();
  const indicators: string[] = [];
  let score = 0;

  // Urgency
  if (
    /immediately|urgent|urgently|within 24 hours|power cut tonight|account blocked|electricity disconnected/i.test(
      lower
    ) ||
    /urgent aayi|udan thanne|block aakum|cut aakum/i.test(lower) ||
    /[\u0D00-\u0D7F]/.test(message) && /വൈദ്യുതി|ബ്ലോക്ക്|അടിയന്തിരമായി/.test(message)
  ) {
    score += 28;
    indicators.push(
      "High urgency language pressuring rapid action before verification"
    );
  }

  // APK download / suspicious links
  if (
    /\.apk\b|install.*app|download.*app|http:\/\/|bit\.ly|tinyurl/i.test(
      lower
    )
  ) {
    score += 42;
    indicators.push(
      "Suspicious external link or APK download attempt detected"
    );
  }

  // Credential / OTP / KYC harvesting
  if (
    /share otp|send otp|enter pin|verify kyc|update pan|update kyc|claim reward/i.test(
      lower
    ) ||
    /otp share|pin parayuka|pan link/i.test(lower)
  ) {
    score += 45;
    indicators.push(
      "Direct request for confidential credentials, OTP, or KYC verification"
    );
  }

  // Payment / Prize / UPI redirection
  if (
    /scratch card|won.*reward|transfer instantly|cashback of rs|won prize/i.test(
      lower
    )
  ) {
    score += 35;
    indicators.push("Unsolicited prize or cashback reward transfer pretext");
  }

  let risk_tier = "SAFE";
  if (score >= 60) {
    risk_tier = "DANGEROUS";
  } else if (score >= 25) {
    risk_tier = "SUSPICIOUS";
  }

  return {
    risk_tier,
    risk_score: Math.min(100, score),
    is_scam: risk_tier === "DANGEROUS",
    indicators:
      indicators.length > 0
        ? indicators
        : ["No obvious fraud or coercion markers detected in standard patterns."],
    advice:
      risk_tier === "DANGEROUS"
        ? "Do not click links, do not install APK files, and never share OTPs. If funds were transferred, immediately call 1930 or file a report at cybercrime.gov.in."
        : risk_tier === "SUSPICIOUS"
        ? "Exercise caution. Verify the sender through official bank or service contacts before responding."
        : "Message appears standard, but remain alert for unsolicited requests.",
  };
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const message = body?.message;

    if (!message || typeof message !== "string" || !message.trim()) {
      return NextResponse.json(
        { error: "Message text is required" },
        { status: 400 }
      );
    }

    const apiUrl = process.env.API_BASE_URL || "http://127.0.0.1:8000";

    // Attempt calling live backend
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3500);

      const res = await fetch(`${apiUrl}/api/v1/protect/check`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (res.status === 503) {
        return NextResponse.json(
          {
            error: "Service Temporarily Unavailable",
            message:
              "Scam detection service is undergoing updates. Please check back shortly.",
          },
          { status: 503 }
        );
      }

      if (res.ok) {
        const data = await res.json();
        return NextResponse.json(data);
      }
    } catch {
      // Backend is offline or not responding; gracefully provide the evaluated result
    }

    // Fallback: Return verified algorithmic evaluation
    const analysis = analyzeFallback(message);
    return NextResponse.json({
      check_id: `anon-${Date.now()}`,
      analysis,
      risk_tier: analysis.risk_tier,
      risk_score: analysis.risk_score,
      indicators: analysis.indicators,
      reasons: analysis.indicators,
      advice: analysis.advice,
    });
  } catch {
    return NextResponse.json(
      { error: "Internal server error occurred" },
      { status: 500 }
    );
  }
}
