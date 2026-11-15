"use client";

import { useBuildings, useParkingLots } from "@/lib/hooks";
import { cx } from "./ui";

interface Props {
  highlight?: Record<number, number>;
  selected?: number | null;
  onSelect?: (buildingId: number) => void;
}

const SCALE = 1.0;

export function CampusMap({ highlight = {}, selected = null, onSelect }: Props) {
  const { data: buildings } = useBuildings();
  const { data: lots } = useParkingLots();
  if (!buildings) return <div className="skeleton h-72" />;
  const nearest = selected ? (lots ?? []).map((lot) => ({ lot, distance: lot.near_json[String(selected)] ?? 9999 })).sort((a, b) => a.distance - b.distance).slice(0, 2) : [];
  return (
    <div>
      <svg viewBox="100 20 560 640" className="h-auto w-full rounded-lg border border-line bg-surface2" role="img" aria-label="Campus map">
        {buildings.map((building) => {
          const count = highlight[building.id] ?? 0;
          const isSelected = selected === building.id;
          return (
            <g key={building.id} transform={`translate(${building.x * SCALE} ${building.y * SCALE})`} onClick={() => onSelect?.(building.id)} className={cx(onSelect && "cursor-pointer")} tabIndex={onSelect ? 0 : -1} onKeyDown={(event) => event.key === "Enter" && onSelect?.(building.id)}>
              <rect x={-38} y={-22} width={76} height={44} rx={8} className={cx("stroke-2", count > 0 ? "fill-goodbg stroke-good" : "fill-surface stroke-line", isSelected && "stroke-primary")} />
              <text textAnchor="middle" y={-3} className="fill-ink text-xs font-medium">
                {building.name.replace("Academic ", "").replace("Complex", "Cx")}
              </text>
              <text textAnchor="middle" y={12} className={cx("text-xs", count > 0 ? "fill-good" : "fill-muted")}>
                {count > 0 ? `${count} free` : building.zone}
              </text>
            </g>
          );
        })}
      </svg>
      {nearest.length > 0 && (
        <p className="mt-2 text-xs text-muted">
          Nearest parking: {nearest.map(({ lot, distance }) => `${lot.name} (${distance} m)`).join(", ")}
        </p>
      )}
    </div>
  );
}
