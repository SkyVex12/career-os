// Simple Plausible event helper (SSR-safe)
export function track(event, props) {
  if (typeof window === "undefined") return;
  const plausibleFn = window.plausible;
  if (typeof plausibleFn !== "function") return;

  if (props && Object.keys(props).length) {
    plausibleFn(event, { props });
  } else {
    plausibleFn(event);
  }
}
