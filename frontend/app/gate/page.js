import { Suspense } from "react";
import GateClient from "./GateClient";

export default function GatePage() {
  return (
    <Suspense fallback={null}>
      <GateClient />
    </Suspense>
  );
}
