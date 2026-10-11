import { test } from "node:test";
import assert from "node:assert/strict";
import { lowBatteryBanner } from "../src/lowBatteryBanner.ts";

test("REQ-DASH-001 shows a low-battery banner below 3300 mV", () => {
  assert.equal(lowBatteryBanner({ stationId: 7, batteryMv: 3250 }), "Station 7: battery low (3.25 V)");
});

test("REQ-DASH-001 shows no banner at or above 3300 mV", () => {
  assert.equal(lowBatteryBanner({ stationId: 7, batteryMv: 3300 }), null);
});
