"use client";

import { useState } from "react";
import Topbar from "@/components/layout/Topbar";

// ── Team data ─────────────────────────────────────────────────────────────────

const TEAM = [
  {
    name: "Yashas Nagesh Gowda",
    role: "Co-Founder & AI Engineer",
    linkedin: "https://www.linkedin.com/in/yashasngowda/",
    email: "yashasgowdanov@gmail.com",
    phone: "+18509006288",
    phoneDisplay: "+1 (850) 900-6288",
    avatarUrl: "https://unavatar.io/linkedin/yashasngowda",
    initials: "YN",
    accent: "#00E5FF",
  },
  {
    name: "Sumith G.S",
    role: "Co-Founder & AI Engineer",
    linkedin: "https://www.linkedin.com/in/sumithgs/",
    email: "sumithgs2000@gmail.com",
    phone: "+18503813548",
    phoneDisplay: "+1 (850) 381-3548",
    avatarUrl: "https://unavatar.io/linkedin/sumithgs",
    initials: "SG",
    accent: "#7C3AED",
  },
];

// ── SVG icons ─────────────────────────────────────────────────────────────────

function LinkedInIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="#0A66C2" xmlns="http://www.w3.org/2000/svg">
      <path d="M20.447 20.452H16.89v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a1.977 1.977 0 01-1.972-1.972 1.977 1.977 0 011.972-1.973 1.977 1.977 0 011.972 1.973 1.977 1.977 0 01-1.972 1.972zm1.709 13.019H3.628V9h3.418v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z" />
    </svg>
  );
}

function EmailIcon({ color }: { color: string }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" xmlns="http://www.w3.org/2000/svg">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#22C55E" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" xmlns="http://www.w3.org/2000/svg">
      <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07A19.5 19.5 0 0 1 4.07 12a19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 3 1.18h3a2 2 0 0 1 2 1.72c.127.96.361 1.903.7 2.81a2 2 0 0 1-.45 2.11L7.09 8.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0 1 21 16l.92.92z" />
    </svg>
  );
}

// ── Animated member card ──────────────────────────────────────────────────────

function TeamCard({ member, delay }: { member: typeof TEAM[0]; delay: number }) {
  const [hovered, setHovered] = useState(false);
  const [imgError, setImgError] = useState(false);

  const isYashas = member.accent === "#00E5FF";

  return (
    <div
      style={{
        animation: `fadeSlideUp 0.6s ease forwards`,
        animationDelay: `${delay}s`,
        opacity: 0,
        flex: "1 1 300px",
        maxWidth: 400,
        width: "100%",
      }}
    >
      {/* Gradient border wrapper */}
      <div
        style={{
          background: hovered
            ? `linear-gradient(135deg, ${member.accent}90, #212C4D, ${member.accent}60)`
            : `linear-gradient(135deg, ${member.accent}40, #212C4D, ${member.accent}20)`,
          padding: "1px",
          borderRadius: 22,
          transition: "background 0.35s ease",
          boxShadow: hovered
            ? `0 0 40px ${member.accent}25, 0 20px 60px rgba(0,0,0,0.4)`
            : `0 0 0px transparent, 0 8px 32px rgba(0,0,0,0.3)`,
        }}
      >
        {/* Card inner */}
        <div
          onMouseEnter={() => setHovered(true)}
          onMouseLeave={() => setHovered(false)}
          style={{
            background: "linear-gradient(160deg, #0D1628 0%, #0A1020 100%)",
            borderRadius: 21,
            padding: "32px 28px 28px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            transform: hovered ? "translateY(-6px)" : "translateY(0px)",
            transition: "transform 0.35s ease",
            cursor: "default",
            position: "relative",
            overflow: "hidden",
          }}
        >
          {/* Top radial glow */}
          <div style={{
            position: "absolute",
            top: -40,
            left: "50%",
            transform: "translateX(-50%)",
            width: 200,
            height: 200,
            borderRadius: "50%",
            background: `radial-gradient(circle, ${member.accent}${hovered ? "18" : "0A"} 0%, transparent 70%)`,
            transition: "background 0.4s ease",
            pointerEvents: "none",
          }} />

          {/* Circuit-line corner decoration (Byte Theory aesthetic) */}
          <svg
            style={{ position: "absolute", top: 12, right: 12, opacity: hovered ? 0.5 : 0.2, transition: "opacity 0.3s" }}
            width="40" height="40" viewBox="0 0 40 40" fill="none"
          >
            <line x1="0" y1="20" x2="16" y2="20" stroke={member.accent} strokeWidth="1.5" />
            <line x1="20" y1="0" x2="20" y2="16" stroke={member.accent} strokeWidth="1.5" />
            <circle cx="20" cy="20" r="4" stroke={member.accent} strokeWidth="1.5" fill="none" />
            <circle cx="20" cy="20" r="1.5" fill={member.accent} />
          </svg>
          <svg
            style={{ position: "absolute", bottom: 12, left: 12, opacity: hovered ? 0.5 : 0.2, transition: "opacity 0.3s" }}
            width="40" height="40" viewBox="0 0 40 40" fill="none"
          >
            <line x1="40" y1="20" x2="24" y2="20" stroke={member.accent} strokeWidth="1.5" />
            <line x1="20" y1="40" x2="20" y2="24" stroke={member.accent} strokeWidth="1.5" />
            <circle cx="20" cy="20" r="4" stroke={member.accent} strokeWidth="1.5" fill="none" />
            <circle cx="20" cy="20" r="1.5" fill={member.accent} />
          </svg>

          {/* Profile picture */}
          <div style={{
            width: 120,
            height: 120,
            borderRadius: "50%",
            marginBottom: 20,
            position: "relative",
            zIndex: 1,
            flexShrink: 0,
            boxShadow: `0 0 0 3px ${member.accent}${hovered ? "AA" : "55"}, 0 0 ${hovered ? "30px" : "16px"} ${member.accent}${hovered ? "40" : "20"}`,
            transition: "box-shadow 0.4s ease",
          }}>
            {!imgError ? (
              <img
                src={member.avatarUrl}
                alt={member.name}
                onError={() => setImgError(true)}
                style={{ width: 120, height: 120, borderRadius: "50%", objectFit: "cover", display: "block" }}
              />
            ) : (
              <div style={{
                width: 120,
                height: 120,
                borderRadius: "50%",
                background: isYashas
                  ? "linear-gradient(135deg, #00E5FF, #0EA5E9)"
                  : "linear-gradient(135deg, #7C3AED, #6C72FF)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 36,
                fontWeight: 700,
                color: "#ffffff",
                letterSpacing: 2,
              }}>
                {member.initials}
              </div>
            )}
          </div>

          {/* Name */}
          <h2 style={{
            color: "#ffffff",
            fontSize: 21,
            fontWeight: 700,
            margin: 0,
            textAlign: "center",
            position: "relative",
            zIndex: 1,
            letterSpacing: "-0.01em",
          }}>
            {member.name}
          </h2>

          {/* Role badge */}
          <div style={{
            marginTop: 8,
            marginBottom: 0,
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            padding: "4px 12px",
            borderRadius: 999,
            background: `${member.accent}15`,
            border: `1px solid ${member.accent}35`,
            position: "relative",
            zIndex: 1,
          }}>
            {/* tiny hex icon */}
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <polygon points="5,1 8.33,2.75 8.33,6.25 5,8 1.67,6.25 1.67,2.75"
                stroke={member.accent} strokeWidth="1" fill={`${member.accent}30`} />
            </svg>
            <span style={{ color: member.accent, fontSize: 12, fontWeight: 600 }}>{member.role}</span>
          </div>

          {/* Divider */}
          <div style={{
            width: "100%",
            height: 1,
            background: `linear-gradient(90deg, transparent, ${member.accent}30, transparent)`,
            margin: "22px 0 18px",
            position: "relative",
            zIndex: 1,
          }} />

          {/* Contact links */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "100%", position: "relative", zIndex: 1 }}>
            <a
              href={member.linkedin}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "9px 14px", borderRadius: 10,
                background: "#0A66C210", border: "1px solid #0A66C230",
                textDecoration: "none", fontSize: 13,
                transition: "background 0.2s, border-color 0.2s",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#0A66C225"; (e.currentTarget as HTMLElement).style.borderColor = "#0A66C250"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "#0A66C210"; (e.currentTarget as HTMLElement).style.borderColor = "#0A66C230"; }}
            >
              <LinkedInIcon />
              <span style={{ color: "#ffffff", fontWeight: 500 }}>LinkedIn Profile</span>
            </a>

            <a
              href={`mailto:${member.email}`}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "9px 14px", borderRadius: 10,
                background: `${member.accent}0F`, border: `1px solid ${member.accent}30`,
                textDecoration: "none", fontSize: 13,
                transition: "background 0.2s, border-color 0.2s",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = `${member.accent}22`; (e.currentTarget as HTMLElement).style.borderColor = `${member.accent}55`; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = `${member.accent}0F`; (e.currentTarget as HTMLElement).style.borderColor = `${member.accent}30`; }}
            >
              <EmailIcon color={member.accent} />
              <span style={{ color: "#ffffff", fontWeight: 500 }}>{member.email}</span>
            </a>

            <a
              href={`tel:${member.phone}`}
              style={{
                display: "flex", alignItems: "center", gap: 12,
                padding: "9px 14px", borderRadius: 10,
                background: "#22C55E10", border: "1px solid #22C55E30",
                textDecoration: "none", fontSize: 13,
                transition: "background 0.2s, border-color 0.2s",
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLElement).style.background = "#22C55E22"; (e.currentTarget as HTMLElement).style.borderColor = "#22C55E55"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = "#22C55E10"; (e.currentTarget as HTMLElement).style.borderColor = "#22C55E30"; }}
            >
              <PhoneIcon />
              <span style={{ color: "#ffffff", fontWeight: 500 }}>{member.phoneDisplay}</span>
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function TeamPage() {
  return (
    <>
      <Topbar title="Meet the Team" />
      <main style={{
        flex: 1,
        overflowY: "auto",
        background: "#060D1F",
        minHeight: 0,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "48px 24px 72px",
      }}>

        {/* ── Hero section ── */}
        <div style={{ textAlign: "center", marginBottom: 52, animation: "fadeSlideUp 0.5s ease forwards" }}>

          {/* Byte Theory logo */}
          <div style={{
            display: "flex",
            justifyContent: "center",
            marginBottom: 28,
            animation: "fadeSlideUp 0.4s ease forwards",
          }}>
            <div style={{
              borderRadius: 16,
              overflow: "hidden",
              boxShadow: "0 0 40px #00E5FF15, 0 0 80px #7C3AED10",
              border: "1px solid #212C4D",
              maxWidth: 340,
              width: "100%",
            }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/byte-theory-logo.svg"
                alt="Byte Theory"
                style={{ width: "100%", display: "block" }}
              />
            </div>
          </div>

          {/* Team tag */}
          <div style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "5px 14px",
            borderRadius: 999,
            background: "#00E5FF10",
            border: "1px solid #00E5FF30",
            color: "#00E5FF",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            marginBottom: 18,
            fontFamily: "'Courier New', monospace",
          }}>
            <span style={{ opacity: 0.7 }}>▸</span> Team Byte Theory
          </div>

          <h1 style={{
            color: "#ffffff",
            fontSize: "clamp(1.9rem, 4.5vw, 3.2rem)",
            fontWeight: 800,
            margin: 0,
            lineHeight: 1.1,
            letterSpacing: "-0.02em",
          }}>
            Meet the Team
          </h1>

          {/* Catchphrase */}
          <p style={{
            fontFamily: "'Courier New', monospace",
            fontSize: "clamp(13px, 2vw, 15px)",
            color: "#7E89AC",
            marginTop: 14,
            marginBottom: 0,
            lineHeight: 1.7,
          }}>
            <span style={{ color: "#00E5FF", opacity: 0.85 }}>byte</span> by{" "}
            <span style={{ color: "#7C3AED", opacity: 0.9 }}>byte</span>
            {", "}we turn{" "}
            <span style={{ color: "#00E5FF", opacity: 0.85 }}>theory</span> into{" "}
            <span style={{ color: "#7C3AED", opacity: 0.9 }}>reality</span>
          </p>

          {/* Subtle binary decoration */}
          <p style={{
            fontFamily: "'Courier New', monospace",
            fontSize: 10,
            color: "#212C4D",
            marginTop: 10,
            letterSpacing: "0.15em",
          }}>
            01110111 01101000 01101001 01101100 01100101 00101000 01100001 01101100 01101001 01110110 01100101 00101001
          </p>
        </div>

        {/* ── Cards ── */}
        <div style={{
          display: "flex",
          flexWrap: "wrap",
          gap: 32,
          justifyContent: "center",
          width: "100%",
          maxWidth: 900,
        }}>
          {TEAM.map((member, i) => (
            <TeamCard key={member.email} member={member} delay={0.1 + i * 0.15} />
          ))}
        </div>

        {/* ── Footer ── */}
        <div style={{
          marginTop: 64,
          textAlign: "center",
          animation: "fadeSlideUp 0.6s ease 0.45s forwards",
          opacity: 0,
        }}>
          {/* Byte Theory catchphrase footer */}
          <p style={{
            fontFamily: "'Courier New', monospace",
            fontSize: 12,
            color: "#7C3AED",
            opacity: 0.7,
            marginBottom: 6,
          }}>
            while(alive) {"{ think(); build(); break(); repeat(); }"}
          </p>
          <p style={{ color: "#7E89AC", fontSize: 13, margin: 0 }}>
            Built with ❤️ using Next.js, FastAPI &amp; Google Gemini 2.5
          </p>
        </div>
      </main>

      <style>{`
        @keyframes fadeSlideUp {
          from { opacity: 0; transform: translateY(24px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes borderGlow {
          0%,  100% { box-shadow: 0 0 20px #00E5FF20, 0 0 60px #7C3AED10; }
          50%        { box-shadow: 0 0 40px #00E5FF35, 0 0 80px #7C3AED20; }
        }
      `}</style>
    </>
  );
}
