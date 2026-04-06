export const nodeLabels = {
  normalize: "Cleaning up your text",
  dedup: "Checking for duplicates",
  classify: "Categorizing entry",
  entities: "Extracting people & projects",
  deadline: "Finding deadlines",
  title_summary: "Generating title & summary",
  extract_relations: "Mapping relations",
  store: "Saving to database",
};

export const entityColors = {
  person: { bg: "#e8e0d4", text: "#5a4a3a" },
  project: { bg: "#d4ddd4", text: "#3a4a3a" },
  place: { bg: "#ddd8cc", text: "#4a453a" },
  organization: { bg: "#d4d8dd", text: "#3a3f4a" },
  task: { bg: "#e0d4d4", text: "#4a3a3a" },
  event: { bg: "#d4dde0", text: "#3a4a4d" },
  tool: { bg: "#ddd4e0", text: "#453a4a" },
};

export const pipelineOrder = [
  "normalize",
  "dedup",
  "classify",
  "entities",
  "deadline",
  "title_summary",
  "extract_relations",
  "store",
];
