import { Component, lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import SealFallback from "./SealFallback";
import type { SealStatus } from "./Seal3D";

const Seal3D = lazy(() => import("./Seal3D"));

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return !!(canvas.getContext("webgl2") || canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false);
  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    if (!mq) return;
    const onChange = () => setReduced(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

class Boundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export default function Seal({ status }: { status: SealStatus }) {
  const [webgl] = useState(hasWebGL);
  const reduced = usePrefersReducedMotion();
  const fallback = <SealFallback status={status} />;
  return (
    <div className={`seal seal--${status}`}>
      {webgl ? (
        <Boundary fallback={fallback}>
          <Suspense fallback={fallback}>
            <Seal3D status={status} reducedMotion={reduced} />
          </Suspense>
        </Boundary>
      ) : (
        fallback
      )}
    </div>
  );
}

export type { SealStatus };
