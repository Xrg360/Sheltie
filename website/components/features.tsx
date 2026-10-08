import { ICONS } from "@/lib/icons";
import type { Feature } from "@/lib/site";

export function FeatureGrid({ features }: { features: Feature[] }) {
  return (
    <div className="grid grid--3">
      {features.map((feature) => {
        const Icon = ICONS[feature.icon];
        return (
          <article className="card" key={feature.title}>
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
