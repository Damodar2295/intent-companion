export function RomeIllustration() {
  return (
    <svg
      className="rome-art"
      viewBox="0 0 540 300"
      fill="none"
      aria-hidden="true"
    >
      <circle cx="386" cy="88" r="69" fill="white" fillOpacity=".055" />
      <circle cx="386" cy="88" r="50" stroke="white" strokeOpacity=".16" />
      <path
        d="M30 260h490M64 248h417M112 230V117c110-59 241-49 321 0v113M112 143c111-56 241-46 321 0M112 171c111-49 241-39 321 0M112 201c111-45 241-35 321 0M112 230c111-34 241-24 321 0"
        stroke="white"
        strokeOpacity=".48"
        strokeWidth="2"
      />
      {[0, 1, 2].map((row) => (
        <g key={row}>
          {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((col) => {
            const x = 130 + col * 33;
            const y = 123 + row * 32 - Math.sin((col / 8) * Math.PI) * 28;
            return (
              <path
                key={col}
                d={`M${x} ${y + 16}v-12a8 8 0 0 1 16 0v12`}
                stroke="white"
                strokeOpacity={0.3 + row * 0.06}
                strokeWidth="2"
              />
            );
          })}
        </g>
      ))}
      <path
        d="M60 245v-66m0 25c-22-3-21-21 0-22 24 1 24 20 0 22M464 241v-82m0 28c-25-3-25-24 0-26 27 2 27 24 0 26"
        stroke="white"
        strokeOpacity=".3"
        strokeWidth="2"
      />
      <path
        d="m304 40 40 9-28 4-12 14 2-15-20-8z"
        fill="white"
        fillOpacity=".65"
      />
      <path
        d="M190 45c40-30 78-32 109-14"
        stroke="white"
        strokeOpacity=".25"
        strokeDasharray="4 6"
      />
    </svg>
  );
}
