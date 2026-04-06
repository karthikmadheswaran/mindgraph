import { useEffect, useMemo, useRef, useState } from "react";
import "../styles/knowledge-graph.css";

const SELF_ID = "you";
const MOBILE_BREAKPOINT = 768;
const MOBILE_HEIGHT = 280;
const DESKTOP_HEIGHT = 380;

function normalizeText(value) {
  return String(value || "").toLowerCase().trim();
}

function slugify(value) {
  return normalizeText(value)
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function truncateLabel(label, max = 14) {
  if (!label) return "";
  if (label.length <= max) return label;
  return `${label.slice(0, max - 3)}...`;
}

function formatShortDate(value) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function getEntityKind(type) {
  if (type === "project") return "project";
  if (type === "person") return "person";
  if (type === "place") return "place";
  return "other";
}

function formatKindLabel(kind) {
  switch (kind) {
    case "self":
      return "Core";
    case "project":
      return "Project";
    case "person":
      return "Person";
    case "place":
      return "Place";
    case "entry":
      return "Entry cluster";
    case "deadline":
      return "Deadline";
    default:
      return "Entity";
  }
}

function getNodeRadius(node, maxMentionCount) {
  if (node.kind === "self") return 22;
  if (node.kind === "deadline") return 10;

  const rawCount = Number(node.mentionCount || node.count || 1);
  const safeCount = Number.isFinite(rawCount) && rawCount > 0 ? rawCount : 1;
  const maxCount = Math.max(1, maxMentionCount);
  const scale = maxCount === 1 ? 0.5 : (safeCount - 1) / (maxCount - 1);

  return 8 + scale * 20;
}

function getLinkDistance(link, nodeById) {
  const target = nodeById.get(
    typeof link.target === "string" ? link.target : link.target?.id
  );

  if (link.kind === "project-deadline") return 66;
  if (link.kind === "entity-entry") return 74;

  switch (target?.kind) {
    case "project":
      return 92;
    case "person":
      return 116;
    case "place":
      return 122;
    case "entry":
      return 156;
    default:
      return 132;
  }
}

function getNodeColors(node) {
  switch (node.kind) {
    case "self":
      return {
        fill: "var(--text-primary, #2c2418)",
        stroke: "rgba(44, 36, 24, 0.18)",
        label: "#fff",
      };
    case "project":
      return {
        fill: "var(--accent, #8a9a7a)",
        stroke: "rgba(107, 93, 77, 0.18)",
        label: "var(--text-primary, #2c2418)",
      };
    case "person":
      return {
        fill: "var(--accent-warm, #c4695a)",
        stroke: "rgba(107, 93, 77, 0.18)",
        label: "#fff",
      };
    case "place":
      return {
        fill: "var(--accent-sand, #d4a574)",
        stroke: "rgba(107, 93, 77, 0.18)",
        label: "var(--text-primary, #2c2418)",
      };
    case "entry":
      return {
        fill: "var(--accent-soft, #d4ddd4)",
        stroke: "rgba(107, 93, 77, 0.18)",
        label: "var(--text-primary, #2c2418)",
      };
    case "deadline":
      return {
        fill: "var(--accent-warm, #c4695a)",
        stroke: "rgba(107, 93, 77, 0.18)",
        label: "#fff",
      };
    default:
      return {
        fill: "var(--border, rgba(107, 93, 77, 0.16))",
        stroke: "rgba(107, 93, 77, 0.34)",
        label: "var(--text-primary, #2c2418)",
      };
  }
}

export default function KnowledgeGraph({
  entities = [],
  entries = [],
  deadlines = [],
}) {
  const shellRef = useRef(null);
  const svgRef = useRef(null);
  const simulationRef = useRef(null);
  const zoomBehaviorRef = useRef(null);
  const d3Ref = useRef(null);
  const transformRef = useRef(null);
  const positionsRef = useRef(new Map());

  const [dimensions, setDimensions] = useState({
    width: 0,
    height: DESKTOP_HEIGHT,
  });
  const [tooltip, setTooltip] = useState(null);
  const [expandedNodeId, setExpandedNodeId] = useState(null);

  const processedEntries = useMemo(
    () => entries.filter((entry) => entry.status !== "processing"),
    [entries]
  );

  const baseGraph = useMemo(() => {
    const entryClusterMap = new Map();
    const sortedDeadlines = [...deadlines].sort((a, b) => {
      const aTime = a?.due_date ? new Date(a.due_date).getTime() : Number.MAX_SAFE_INTEGER;
      const bTime = b?.due_date ? new Date(b.due_date).getTime() : Number.MAX_SAFE_INTEGER;
      return aTime - bTime;
    });

    processedEntries.forEach((entry, index) => {
      const title = String(entry.auto_title || "Untitled Entry").trim() || "Untitled Entry";
      const key = normalizeText(title) || `untitled-${index}`;
      const existing = entryClusterMap.get(key);
      const createdAt = entry.created_at || null;

      if (existing) {
        existing.count += 1;
        existing.mentionCount += 1;
        existing.entries.push(entry);

        if (
          createdAt &&
          (!existing.lastMentioned ||
            new Date(createdAt).getTime() >
              new Date(existing.lastMentioned).getTime())
        ) {
          existing.lastMentioned = createdAt;
        }
      } else {
        entryClusterMap.set(key, {
          id: `entry-${slugify(title) || `cluster-${index}`}`,
          nodeId: `entry-${slugify(title) || `cluster-${index}`}`,
          key,
          label: title,
          kind: "entry",
          count: 1,
          mentionCount: 1,
          lastMentioned: createdAt,
          entries: [entry],
        });
      }
    });

    const entityNodes = entities.map((entity, index) => {
      const kind = getEntityKind(entity.entity_type);
      const label = entity.name || `Entity ${index + 1}`;
      const nodeId =
        entity.id != null
          ? `${kind}-${entity.id}`
          : `${kind}-${slugify(label) || index}`;
      const mentionCount = Number(entity.mention_count || 1) || 1;
      const lastMentioned =
        entity.last_mentioned_at ||
        entity.last_seen_at ||
        entity.updated_at ||
        entity.created_at ||
        entity.first_seen_at ||
        null;
      const linkedDeadlines =
        kind === "project"
          ? sortedDeadlines.filter((deadline) =>
              normalizeText(deadline.description).includes(normalizeText(label))
            )
          : [];

      return {
        id: nodeId,
        sourceId: entity.id,
        label,
        kind,
        mentionCount,
        lastMentioned,
        linkedDeadlines,
        deadline: linkedDeadlines[0] || null,
      };
    });

    const entryNodes = Array.from(entryClusterMap.values())
      .sort((a, b) => {
        const countDiff = (b.count || 0) - (a.count || 0);
        if (countDiff !== 0) return countDiff;

        const aTime = a.lastMentioned ? new Date(a.lastMentioned).getTime() : 0;
        const bTime = b.lastMentioned ? new Date(b.lastMentioned).getTime() : 0;
        return bTime - aTime;
      })
      .map((cluster) => ({
        ...cluster,
        id: cluster.nodeId,
      }));

    const selfNode = {
      id: SELF_ID,
      label: "You",
      kind: "self",
      mentionCount: 0,
      lastMentioned: null,
    };

    const nodes = [selfNode, ...entityNodes, ...entryNodes];
    const links = nodes
      .filter((node) => node.id !== SELF_ID)
      .map((node) => ({
        id: `link-${SELF_ID}-${node.id}`,
        source: SELF_ID,
        target: node.id,
        kind: "primary",
      }));

    return {
      nodes,
      links,
      nodeMap: new Map(nodes.map((node) => [node.id, node])),
      entryClusters: entryNodes,
    };
  }, [deadlines, entities, processedEntries]);

  const expansion = useMemo(() => {
    if (!expandedNodeId) {
      return { nodes: [], links: [], connectedNodeIds: new Set() };
    }

    const expandedNode = baseGraph.nodeMap.get(expandedNodeId);
    if (!expandedNode || expandedNode.kind === "self") {
      return { nodes: [], links: [], connectedNodeIds: new Set() };
    }

    if (expandedNode.kind === "project" && expandedNode.linkedDeadlines?.length) {
      const deadlineNodes = expandedNode.linkedDeadlines.map((deadline, index) => ({
        id: `deadline-${expandedNode.id}-${deadline.id ?? index}`,
        label: formatShortDate(deadline.due_date) || truncateLabel(deadline.description, 10) || "Due",
        kind: "deadline",
        mentionCount: 1,
        dueDate: deadline.due_date,
        description: deadline.description,
        parentId: expandedNode.id,
      }));

      return {
        nodes: deadlineNodes,
        links: deadlineNodes.map((node) => ({
          id: `link-${expandedNode.id}-${node.id}`,
          source: expandedNode.id,
          target: node.id,
          kind: "project-deadline",
        })),
        connectedNodeIds: new Set(),
      };
    }

    if (expandedNode.kind === "person" || expandedNode.kind === "place") {
      const needle = normalizeText(expandedNode.label);
      const connectedNodeIds = new Set();

      baseGraph.entryClusters.forEach((cluster) => {
        const hasMatch = cluster.entries.some((entry) =>
          normalizeText(`${entry.auto_title || ""} ${entry.raw_text || ""}`).includes(
            needle
          )
        );

        if (hasMatch) {
          connectedNodeIds.add(cluster.id);
        }
      });

      return {
        nodes: [],
        links: Array.from(connectedNodeIds).map((targetId) => ({
          id: `link-${expandedNode.id}-${targetId}`,
          source: expandedNode.id,
          target: targetId,
          kind: "entity-entry",
        })),
        connectedNodeIds,
      };
    }

    return { nodes: [], links: [], connectedNodeIds: new Set() };
  }, [baseGraph.entryClusters, baseGraph.nodeMap, expandedNodeId]);

  const graphNodes = useMemo(
    () => [...baseGraph.nodes, ...expansion.nodes],
    [baseGraph.nodes, expansion.nodes]
  );

  const graphLinks = useMemo(
    () => [...baseGraph.links, ...expansion.links],
    [baseGraph.links, expansion.links]
  );

  const maxMentionCount = useMemo(() => {
    return graphNodes.reduce((maxValue, node) => {
      if (node.kind === "self" || node.kind === "deadline") return maxValue;
      const value = Number(node.mentionCount || node.count || 1) || 1;
      return Math.max(maxValue, value);
    }, 1);
  }, [graphNodes]);

  const hasData = entities.length > 0 || processedEntries.length > 0;

  useEffect(() => {
    if (expandedNodeId && !baseGraph.nodeMap.has(expandedNodeId)) {
      setExpandedNodeId(null);
    }
  }, [baseGraph.nodeMap, expandedNodeId]);

  useEffect(() => {
    const element = shellRef.current;
    if (!element) return undefined;

    const measure = () => {
      const rect = element.getBoundingClientRect();
      const width = Math.round(rect.width);
      const height =
        Math.round(rect.height) ||
        (window.innerWidth <= MOBILE_BREAKPOINT ? MOBILE_HEIGHT : DESKTOP_HEIGHT);

      setDimensions((current) => {
        if (current.width === width && current.height === height) {
          return current;
        }
        return { width, height };
      });
    };

    measure();

    if (typeof ResizeObserver !== "undefined") {
      const observer = new ResizeObserver(() => measure());
      observer.observe(element);
      return () => observer.disconnect();
    }

    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    if (!svgRef.current || dimensions.width <= 0 || dimensions.height <= 0) {
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
      return undefined;
    }

    let cancelled = false;

    const initializeGraph = async () => {
      const d3 = d3Ref.current || (await import("d3"));
      d3Ref.current = d3;

      if (cancelled || !svgRef.current) return;

      if (simulationRef.current) {
        simulationRef.current.stop();
      }

      const svg = d3.select(svgRef.current);
      svg.selectAll("*").remove();
      svg.on(".zoom", null);
      svg
        .attr("width", "100%")
        .attr("height", "100%")
        .attr("viewBox", [0, 0, dimensions.width, dimensions.height])
        .attr("preserveAspectRatio", "xMidYMid meet");

      const viewport = svg
        .append("g")
        .attr("class", "knowledge-graph-viewport");

      const transform = transformRef.current || d3.zoomIdentity;
      viewport.attr("transform", transform);

      const zoom = d3
        .zoom()
        .scaleExtent([0.3, 3])
        .on("zoom", (event) => {
          transformRef.current = event.transform;
          viewport.attr("transform", event.transform);
        });

      zoomBehaviorRef.current = zoom;
      svg.call(zoom).call(zoom.transform, transform);

      const nodes = graphNodes.map((node, index) => {
        const radius = getNodeRadius(node, maxMentionCount);
        const previousPosition = positionsRef.current.get(node.id);
        const parentPosition = node.parentId
          ? positionsRef.current.get(node.parentId)
          : null;
        const angle = (index / Math.max(1, graphNodes.length - 1)) * Math.PI * 2;
        const radialDistance =
          node.kind === "project"
            ? 96
            : node.kind === "entry"
              ? 154
              : node.kind === "deadline"
                ? 56
                : 122;

        const x =
          previousPosition?.x ??
          (parentPosition
            ? parentPosition.x + Math.cos(angle) * radialDistance
            : dimensions.width / 2 + Math.cos(angle) * radialDistance);
        const y =
          previousPosition?.y ??
          (parentPosition
            ? parentPosition.y + Math.sin(angle) * radialDistance
            : dimensions.height / 2 + Math.sin(angle) * radialDistance);

        return {
          ...node,
          radius,
          x,
          y,
        };
      });

      const nodeById = new Map(nodes.map((node) => [node.id, node]));
      const links = graphLinks.map((link) => ({
        ...link,
        source: typeof link.source === "string" ? link.source : link.source.id,
        target: typeof link.target === "string" ? link.target : link.target.id,
      }));

      const linkLayer = viewport.append("g").attr("class", "knowledge-link-layer");
      const nodeLayer = viewport.append("g").attr("class", "knowledge-node-layer");

      const linkSelection = linkLayer
        .selectAll("line")
        .data(links, (link) => link.id)
        .join("line")
        .attr("class", (link) =>
          link.kind === "entity-entry"
            ? "knowledge-link knowledge-link-expanded"
            : "knowledge-link"
        )
        .attr("vector-effect", "non-scaling-stroke");

      const simulation = d3
        .forceSimulation(nodes)
        .force(
          "link",
          d3
            .forceLink(links)
            .id((node) => node.id)
            .distance((link) => getLinkDistance(link, nodeById))
            .strength((link) => (link.kind === "entity-entry" ? 0.22 : 0.14))
        )
        .force(
          "charge",
          d3.forceManyBody().strength((node) => {
            if (node.kind === "self") return -240;
            if (node.kind === "deadline") return -60;
            return -120;
          })
        )
        .force("center", d3.forceCenter(dimensions.width / 2, dimensions.height / 2))
        .force(
          "collision",
          d3.forceCollide().radius((node) => node.radius + 16)
        )
        .force(
          "x",
          d3
            .forceX(dimensions.width / 2)
            .strength((node) => (node.kind === "self" ? 0.36 : 0.03))
        )
        .force(
          "y",
          d3
            .forceY(dimensions.height / 2)
            .strength((node) => (node.kind === "self" ? 0.36 : 0.03))
        )
        .alpha(1)
        .alphaTarget(0);

      simulationRef.current = simulation;

      const dragBehavior = d3
        .drag()
        .on("start", (event, node) => {
          if (!event.active) {
            simulation.alphaTarget(0.3).restart();
          }
          node.fx = node.x;
          node.fy = node.y;
        })
        .on("drag", (event, node) => {
          node.fx = event.x;
          node.fy = event.y;
        })
        .on("end", (event, node) => {
          if (!event.active) {
            simulation.alphaTarget(0);
          }

          if (node.kind === "self") {
            node.fx = null;
            node.fy = null;
          } else {
            node.fx = null;
            node.fy = null;
          }
        });

      const nodeSelection = nodeLayer
        .selectAll("g")
        .data(nodes, (node) => node.id)
        .join("g")
        .attr("class", (node) => {
          const classes = [`knowledge-node`, `knowledge-node--${node.kind}`];
          if (node.id === expandedNodeId) classes.push("is-expanded");
          if (expansion.connectedNodeIds.has(node.id)) classes.push("is-connected");
          return classes.join(" ");
        })
        .style("opacity", 0)
        .style("cursor", (node) =>
          node.kind === "self" ? "grab" : node.kind === "deadline" ? "pointer" : "pointer"
        )
        .call(dragBehavior)
        .on("click", (event, node) => {
          event.stopPropagation();
          if (node.kind === "self" || node.kind === "deadline") return;
          setExpandedNodeId((current) => (current === node.id ? null : node.id));
        })
        .on("mouseenter", (event, node) => {
          if (node.kind === "self") return;

          const [x, y] = d3.pointer(event, shellRef.current);
          setTooltip({
            node,
            x: x + 16,
            y: y + 16,
          });
        })
        .on("mousemove", (event, node) => {
          if (node.kind === "self") return;

          const [x, y] = d3.pointer(event, shellRef.current);
          setTooltip({
            node,
            x: x + 16,
            y: y + 16,
          });
        })
        .on("mouseleave", () => {
          setTooltip(null);
        });

      nodeSelection
        .append("circle")
        .attr("class", "knowledge-node-ring")
        .attr("r", (node) => node.radius + 7)
        .attr("fill", "none")
        .attr("stroke", "var(--accent-warm, #c4695a)")
        .attr("stroke-width", 1.4)
        .attr("stroke-opacity", 0);

      nodeSelection
        .append("circle")
        .attr("class", "knowledge-node-core")
        .attr("r", (node) => node.radius)
        .attr("fill", (node) => getNodeColors(node).fill)
        .attr("stroke", (node) => getNodeColors(node).stroke)
        .attr("stroke-width", (node) =>
          node.id === expandedNodeId || expansion.connectedNodeIds.has(node.id) ? 2 : 1.25
        );

      nodeSelection
        .append("circle")
        .attr("class", "knowledge-node-deadline-badge")
        .attr("r", (node) => (node.deadline ? 4 : 0))
        .attr("cx", (node) => node.radius * 0.72)
        .attr("cy", (node) => -node.radius * 0.72)
        .attr("fill", "var(--accent-warm, #c4695a)");

      nodeSelection
        .append("text")
        .attr("class", (node) =>
          node.kind === "self"
            ? "knowledge-node-label knowledge-node-label-self"
            : "knowledge-node-label"
        )
        .attr("text-anchor", "middle")
        .attr("y", (node) => node.radius + 10)
        .attr("fill", (node) => getNodeColors(node).label)
        .text((node) => truncateLabel(node.label));

      nodeSelection
        .transition()
        .delay((_, index) => index * 45)
        .duration(420)
        .style("opacity", 1);

      simulation.on("tick", () => {
        nodes.forEach((node) => {
          const padding = node.kind === "self" ? 26 : 18;
          node.x = Math.max(
            node.radius + padding,
            Math.min(dimensions.width - node.radius - padding, node.x)
          );
          node.y = Math.max(
            node.radius + padding,
            Math.min(dimensions.height - node.radius - padding, node.y)
          );

          positionsRef.current.set(node.id, { x: node.x, y: node.y });
        });

        linkSelection
          .attr("x1", (link) => link.source.x)
          .attr("y1", (link) => link.source.y)
          .attr("x2", (link) => link.target.x)
          .attr("y2", (link) => link.target.y);

        nodeSelection.attr("transform", (node) => `translate(${node.x}, ${node.y})`);
      });
    };

    initializeGraph();

    return () => {
      cancelled = true;
      setTooltip(null);
      if (simulationRef.current) {
        simulationRef.current.stop();
      }
    };
  }, [
    dimensions.height,
    dimensions.width,
    expandedNodeId,
    expansion.connectedNodeIds,
    graphLinks,
    graphNodes,
    maxMentionCount,
  ]);

  const handleResetZoom = () => {
    if (!svgRef.current || !zoomBehaviorRef.current || !d3Ref.current) return;

    transformRef.current = d3Ref.current.zoomIdentity;
    d3Ref.current
      .select(svgRef.current)
      .transition()
      .duration(450)
      .call(zoomBehaviorRef.current.transform, d3Ref.current.zoomIdentity);
  };

  const tooltipContent = tooltip?.node
    ? {
        title: tooltip.node.label,
        kind: formatKindLabel(tooltip.node.kind),
        mentions:
          tooltip.node.kind === "entry"
            ? tooltip.node.count || tooltip.node.mentionCount || 1
            : tooltip.node.mentionCount || 1,
        lastMentioned: tooltip.node.dueDate
          ? ""
          : formatShortDate(tooltip.node.lastMentioned),
        dueDate: formatShortDate(
          tooltip.node.dueDate || tooltip.node.deadline?.due_date
        ),
      }
    : null;

  return (
    <section className="knowledge-graph-section">
      <div className="knowledge-graph-header">
        <div>
          <h2 className="knowledge-graph-title">Your Mind Lately</h2>
          <p className="knowledge-graph-subtitle">
            Click a node to explore connections. Drag to rearrange.
          </p>
        </div>
      </div>

      <div ref={shellRef} className="knowledge-graph-shell">
        <button
          type="button"
          className="knowledge-graph-reset"
          onClick={handleResetZoom}
        >
          Reset view
        </button>

        <svg
          ref={svgRef}
          className="knowledge-graph-svg"
          aria-label="Interactive knowledge graph"
        />

        {!hasData && (
          <div className="knowledge-graph-empty-note">
            Start journaling to see your knowledge graph grow.
          </div>
        )}

        {tooltipContent && (
          <div
            className="knowledge-graph-tooltip"
            style={{
              left: tooltip.x,
              top: tooltip.y,
            }}
          >
            <div className="knowledge-graph-tooltip-title">
              {tooltipContent.title}
            </div>
            <div className="knowledge-graph-tooltip-kind">
              {tooltipContent.kind}
            </div>
            <div className="knowledge-graph-tooltip-line">
              Mention count: {tooltipContent.mentions}
            </div>
            {tooltipContent.lastMentioned && (
              <div className="knowledge-graph-tooltip-line">
                Last mentioned: {tooltipContent.lastMentioned}
              </div>
            )}
            {tooltipContent.dueDate && (
              <div className="knowledge-graph-tooltip-line">
                Due: {tooltipContent.dueDate}
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
