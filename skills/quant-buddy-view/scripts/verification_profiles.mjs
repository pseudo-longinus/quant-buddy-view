const ALL_VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 1000, mobile: false },
  { name: 'mobile390', width: 390, height: 844, mobile: true },
  { name: 'mobile320', width: 320, height: 720, mobile: true },
];

const PROFILES = {
  full: {
    viewports: ALL_VIEWPORTS,
    checkLayout: true,
    cardRuntimeOnly: false,
  },
  'fork-local': {
    viewports: [ALL_VIEWPORTS[0], ALL_VIEWPORTS[2]],
    checkLayout: true,
    cardRuntimeOnly: false,
  },
  'public-smoke': {
    viewports: [{ name: 'publicSmoke', width: 1280, height: 800, mobile: false }],
    checkLayout: false,
    cardRuntimeOnly: false,
  },
  'live-only': {
    viewports: [],
    checkLayout: false,
    cardRuntimeOnly: true,
  },
};

export function resolveVerificationProfile(name = 'full') {
  const normalized = String(name || 'full').trim().toLowerCase();
  const profile = PROFILES[normalized];
  if (!profile) {
    const error = new Error(`unknown verification profile: ${name}`);
    error.code = 'UNKNOWN_VERIFICATION_PROFILE';
    throw error;
  }
  return {
    name: normalized,
    viewports: profile.viewports.map(viewport => ({ ...viewport })),
    checkLayout: profile.checkLayout,
    cardRuntimeOnly: profile.cardRuntimeOnly,
  };
}
