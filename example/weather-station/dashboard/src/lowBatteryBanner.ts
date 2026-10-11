export const LOW_BATTERY_MV = 3300;

export interface StationStatus {
  stationId: number;
  batteryMv: number;
}

export function lowBatteryBanner(s: StationStatus): string | null {
  if (s.batteryMv >= LOW_BATTERY_MV) return null;
  return `Station ${s.stationId}: battery low (${(s.batteryMv / 1000).toFixed(2)} V)`;
}
