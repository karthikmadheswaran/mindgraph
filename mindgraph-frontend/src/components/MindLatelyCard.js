import "../styles/mindmap.css";

function MindLatelyCard({ nodes, selectedNodeId, onSelectNode }) {
  const selectedNode =
    nodes.find((node) => node.id === selectedNodeId) || nodes[0] || null;

  const nonCenterNodes = nodes.filter((node) => node.kind !== "self");

  const getNodeClass = (kind) => {
    if (kind === "self") return "mind-node self";
    if (kind === "project") return "mind-node project";
    return "mind-node entity";
  };

  const renderDetail = (node) => {
    if (!node) {
      return "A gentle snapshot of what your mind has been orbiting around lately.";
    }

    if (node.kind === "self") {
      return "You are at the center of this snapshot - the projects, people, places, and ideas your mind has been returning to recently.";
    }

    const mentionText =
      node.mentionCount && node.mentionCount > 0
        ? `Mentioned ${node.mentionCount} time${node.mentionCount > 1 ? "s" : ""}`
        : "Recently active";

    const recentText = node.lastMentionedLabel
      ? ` - last seen ${node.lastMentionedLabel}`
      : "";

    if (node.kind === "project") {
      return `${node.label} is one of your most recent active projects. ${mentionText}${recentText}.`;
    }

    return `${node.label} is showing up in your recent mental landscape. ${mentionText}${recentText}.`;
  };

  return (
    <div className="grid-card mind-card">
      <div className="mind-card-header">
        <div>
          <h3>Your Mind Lately</h3>
          <p className="mind-card-subtext">
            A calm snapshot of what has been most present recently.
          </p>
        </div>
      </div>

      <div className="mind-map-shell">
        <svg
          className="mind-lines"
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {nonCenterNodes.map((node, index) => {
            const curveX = node.x < 50 ? node.x + 10 : node.x - 10;
            const curveY = node.y < 46 ? node.y + 8 : node.y - 8;

            return (
              <path
                key={node.id}
                d={`M 50 46 Q ${curveX} ${curveY}, ${node.x} ${node.y}`}
                className="mind-line"
                style={{
                  opacity: selectedNodeId === node.id ? 0.9 : 0.5,
                  transitionDelay: `${index * 40}ms`,
                }}
              />
            );
          })}
        </svg>

        {nodes.map((node) => (
          <button
            key={node.id}
            type="button"
            className={`${getNodeClass(node.kind)}${
              selectedNodeId === node.id ? " active" : ""
            }`}
            style={{
              left: `${node.x}%`,
              top: `${node.y}%`,
            }}
            onClick={() => onSelectNode(node.id)}
            title={node.label}
          >
            <span className="mind-node-label">{node.label}</span>
            {node.kind !== "self" && node.mentionCount > 1 && (
              <span className="mind-node-count">{node.mentionCount}</span>
            )}
          </button>
        ))}
      </div>

      <div className="mind-detail-box">{renderDetail(selectedNode)}</div>
    </div>
  );
}

export default MindLatelyCard;
