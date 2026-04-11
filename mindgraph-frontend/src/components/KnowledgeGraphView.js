import { useEffect, useState } from "react";
import { API, authHeaders } from "../utils/auth";
import AnimatedView from "./AnimatedView";
import KnowledgeGraph from "./KnowledgeGraph";

export default function KnowledgeGraphView({ isActive }) {
  const [data, setData] = useState({
    entities: [],
    entries: [],
    deadlines: [],
    relations: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isActive) return undefined;

    let cancelled = false;

    const loadGraphData = async () => {
      setLoading(true);
      setError("");

      try {
        const headers = await authHeaders();
        const [entitiesRes, entriesRes, deadlinesRes, relationsRes] =
          await Promise.all([
            fetch(`${API}/entities`, { headers }),
            fetch(`${API}/entries`, { headers }),
            fetch(`${API}/deadlines`, { headers }),
            fetch(`${API}/entity-relations`, { headers }),
          ]);

        if (
          !entitiesRes.ok ||
          !entriesRes.ok ||
          !deadlinesRes.ok ||
          !relationsRes.ok
        ) {
          throw new Error("Failed to load graph data");
        }

        const [entitiesData, entriesData, deadlinesData, relationsData] =
          await Promise.all([
            entitiesRes.json(),
            entriesRes.json(),
            deadlinesRes.json(),
            relationsRes.json(),
          ]);

        if (!cancelled) {
          setData({
            entities: entitiesData.entities || [],
            entries: entriesData.entries || [],
            deadlines: deadlinesData.deadlines || [],
            relations: relationsData.relations || [],
          });
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message || "Failed to load graph");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    loadGraphData();

    return () => {
      cancelled = true;
    };
  }, [isActive]);

  return (
    <AnimatedView viewKey="graph" isActive={isActive}>
      <div className="dashboard-page">
        <section className="dashboard-section">
          <div className="dashboard-section-header">
            <div>
              <p className="dashboard-kicker">Knowledge Graph</p>
              <h2 className="dashboard-title">Your connected mind</h2>
            </div>
          </div>

          {loading && (
            <div className="dashboard-loading">
              <span className="spinner" />
              <p>Loading your graph...</p>
            </div>
          )}

          {!loading && error && (
            <div className="dashboard-empty">
              <p>{error}</p>
            </div>
          )}

          {!loading && !error && <KnowledgeGraph {...data} />}
        </section>
      </div>
    </AnimatedView>
  );
}
