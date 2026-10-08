import { ICONS } from "@/lib/icons";
import type { Feature } from "@/lib/site";

// Brand cards cycle in this order so no two neighbours share a color (DESIGN.md "Brand palette").
const TONES = ["ink", "lavender", "peach", "ochre", "pink"] as const;

export function FeatureGrid({ features }: { features: Feature[] }) {
  return (
    <div className="grid grid--3">
      {features.map((feature, index) => {
        const Icon = ICONS[feature.icon];
        return (
          <article className={`card card--brand card--${TONES[index % TONES.length]}`} key={feature.title}>
            <span className="card__icon" aria-hidden="true">
              <Icon size={20} />
            </span>
            <h3>
              {feature.title} {feature.status === "planned" ? <span className="pill">Planned</span> : null}
            </h3>
            <p className="muted">{feature.body}</p>
          </article>
        );
      })}
    </div>
  );
}
