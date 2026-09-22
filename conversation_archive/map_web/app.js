/* Local-only view. Archive strings are always textContent, never HTML or script. */
"use strict";
const $ = id => document.getElementById(id);
const token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
let cy, focus = null, graph = null, graphTicket = 0, searchTicket = 0, detailTicket = 0, offset = 0;
const label = value => String(value || "").replaceAll("_", " ");
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}
function button(text, action) {
  const b = element("button", text);
  b.type = "button";
  b.addEventListener("click", action);
  return b;
}
async function api(route, params = {}) {
  const response = await fetch("/api/" + route + "?" + new URLSearchParams(params), {
    headers: {"X-Archive-Token": token}, cache: "no-store", credentials: "omit", mode: "same-origin"
  });
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "Local query failed");
  return value;
}
function error(err) {
  ++graphTicket; ++searchTicket; ++detailTicket;
  $("notice").textContent = err.message;
  $("notice").className = "error";
  if (cy) cy.elements().remove();
  graph = null;
  $("node-list").replaceChildren(); $("edge-list").replaceChildren();
  $("results").replaceChildren(); $("more").hidden = true;
  $("inspector").replaceChildren(element("h2", "Data unavailable"), element("p", err.message));
  $("graph-count").textContent = "No current graph displayed";
}
function sourceDetails(parent, title, value) {
  const box = element("details");
  box.append(element("summary", title), element("pre", JSON.stringify(value, null, 2), "source-json"));
  parent.append(box);
}
async function inspectNode(id) {
  const ticket = ++detailTicket;
  const data = await api("node", {id});
  if (ticket !== detailTicket) return;
  const panel = $("inspector"); panel.replaceChildren();
  panel.append(element("span", "ENTRY & SOURCE", "eyebrow"), element("h2", data.label),
    element("span", label(data.kind), "badge"), element("p", data.id, "key"),
    button("Focus on this node", () => choose(id).catch(error)));
  if (data.text) panel.append(element("h3", "Exact stored text"), element("pre", data.text));
  else panel.append(element("p", "This entity is recorded by scoped rules. Select a connected link to inspect the supporting excerpts and answers."));
  sourceDetails(panel, "Original structured record", data.source_record);
  panel.append(element("p", "Read only. Corrections belong in the prepared question/review workflow.", "small"));
}
async function inspectEdge(id) {
  const ticket = ++detailTicket;
  const data = await api("edge", {id});
  if (ticket !== detailTicket) return;
  const panel = $("inspector"); panel.replaceChildren();
  panel.append(element("span", "RELATIONSHIP EVIDENCE", "eyebrow"),
    element("h2", label(data.relation)), element("span", label(data.status), "badge"),
    element("p", data.source + " → " + data.target, "key"),
    element("p", "Origin: " + label(data.origin), "small"));
  if (data.payload.note) panel.append(element("p", data.payload.note, "small"));
  if (data.payload.reason) panel.append(element("p", data.payload.reason));
  const witnesses = data.payload.evidence || [];
  panel.append(element("h3", "Exact evidence · " + witnesses.length + " excerpt(s)"));
  for (const q of witnesses) {
    const item = element("div", undefined, "quote");
    item.append(button(q.entry_id, () => inspectNode("entry:" + q.entry_id).catch(error)),
      element("pre", q.quote), element("p", "Characters " + q.start + "–" + q.end + " within the indexed entry", "small"));
    panel.append(item);
  }
  if (!witnesses.length) panel.append(element("p", "This contextual association is supported by a recorded answer, not an invented source quotation.", "small"));
  panel.append(element("h3", "Supporting answers · " + data.supporting_answers.length));
  for (const rule of data.supporting_answers) {
    panel.append(element("p", rule.rule_id + " · " + rule.actor, "key"), element("pre", rule.answer));
    sourceDetails(panel, "Rule scope and dependencies", rule.operation);
  }
  sourceDetails(panel, "Full relationship record", data.payload);
}
function draw(data) {
  graph = data;
  const names = new Map(data.nodes.map(n => [n.id, n.entry_id || n.label]));
  const elements = [
    ...data.nodes.map(n => ({data: {id: n.id, kind: n.kind, label: n.kind === "entry" ? n.entry_id + "\n" + n.label.slice(0, 34) : n.label, focus: n.id === focus ? 1 : 0}})),
    ...data.edges.map(e => ({data: {...e, label: label(e.relation)}}))
  ];
  cy.elements().remove(); cy.add(elements);
  cy.layout({name: "concentric", animate: false, padding: 35, minNodeSpacing: 35,
    nodeDimensionsIncludeLabels: true, concentric: n => n.id() === focus ? 100 : n.degree(),
    levelWidth: () => 15}).run();
  const root = data.nodes.find(n => n.id === focus);
  $("focus-title").textContent = root ? root.label : "Focused map";
  $("graph-count").textContent = data.nodes.length + " nodes · " + data.edges.length + " connections" + (data.truncated ? " · LIMIT REACHED" : "");
  $("notice").className = "";
  $("notice").textContent = data.truncated ? "Partial neighborhood shown: refine the focus or filters. Omitted links have not been rejected." : "Explore connections without merging entries. Select any line to inspect its support.";
  $("node-list").replaceChildren(...data.nodes.map(n => button(label(n.kind) + " · " + n.label, () => choose(n.id).catch(error))));
  $("edge-list").replaceChildren(...data.edges.map(e => button((names.get(e.source) || e.source) + " → " + (names.get(e.target) || e.target) + " · " + label(e.relation) + " · " + label(e.status), () => inspectEdge(e.id).catch(error))));
}
async function refreshGraph() {
  if (!focus) return;
  const ticket = ++graphTicket;
  const mode = $("status").value;
  const statuses = ["observed_text", "user_confirmed"];
  if (mode === "derived" || mode === "all") statuses.push("derived");
  if (mode === "proposed" || mode === "all") statuses.push("proposed");
  if (mode === "all") statuses.push("rejected");
  const data = await api("graph", {id: focus, depth: $("depth").value,
    statuses: statuses.join(","), mentions: $("mentions").checked ? "1" : "0", relation: $("relation").value});
  if (ticket === graphTicket) draw(data);
}
async function choose(id) {
  focus = id;
  for (const b of $("results").children) b.classList.toggle("selected", b.dataset.id === id);
  await Promise.all([refreshGraph(), inspectNode(id)]);
}
async function search(append = false) {
  const ticket = ++searchTicket;
  if (!append) offset = 0;
  const data = await api("search", {q: $("search").value, kind: $("kind").value, limit: 20, offset});
  if (ticket !== searchTicket) return;
  if (!append) $("results").replaceChildren();
  for (const n of data.nodes) {
    const b = button("", () => choose(n.id).catch(error));
    b.className = "result"; b.dataset.id = n.id;
    b.classList.toggle("selected", n.id === focus);
    b.append(element("small", label(n.kind) + (n.entry_id ? " · " + n.entry_id : "")), element("strong", n.label));
    $("results").append(b);
  }
  offset += data.nodes.length;
  $("search-count").textContent = offset + " result(s) shown" + (data.has_more ? " · more available" : "");
  $("more").hidden = !data.has_more;
}
async function start() {
  if (!token) throw new Error("Open the complete session URL printed by knowledge_map serve. The token stays in the URL fragment, not in requests or logs.");
  cy = cytoscape({container: $("cy"), elements: [], minZoom: .15, maxZoom: 3,
    style: [
      {selector: "node", style: {label: "data(label)", "font-family": "system-ui", "font-size": 12, "text-wrap": "wrap", "text-max-width": 120, "text-valign": "center", "text-halign": "center", width: 135, height: 55, "background-color": "#d7ede9", color: "#174b47", "border-width": 1, "border-color": "#71a69e", shape: "ellipse"}},
      {selector: 'node[kind="entry"]', style: {shape: "round-rectangle", width: 140, height: 65, "background-color": "#fff", "border-color": "#b7cbd0", color: "#29424e", "font-size": 10}},
      {selector: 'node[kind="mention"]', style: {shape: "diamond", width: 80, height: 45, "background-color": "#f4eede", "border-color": "#c3ae75", "font-size": 10}},
      {selector: 'node[focus=1]', style: {"border-width": 3, "border-color": "#147d78", "font-weight": 700}},
      {selector: "edge", style: {width: 1.7, "line-color": "#83a8a2", "target-arrow-color": "#83a8a2", "target-arrow-shape": "triangle", "curve-style": "bezier", "arrow-scale": .8}},
      {selector: 'edge[status="proposed"]', style: {"line-style": "dashed", "line-color": "#b78435", "target-arrow-color": "#b78435"}},
      {selector: 'edge[status="derived"]', style: {"line-style": "dashed", "line-color": "#8092a7", "target-arrow-color": "#8092a7"}},
      {selector: 'edge[status="rejected"]', style: {"line-style": "dotted", "line-color": "#b77480", "target-arrow-color": "#b77480"}},
      {selector: "edge:selected", style: {"line-color": "#c27f17", "target-arrow-color": "#c27f17", width: 3}},
      {selector: "node:selected", style: {"border-color": "#c27f17", "border-width": 3}}
    ]});
  let resizeFrame;
  const observer = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame);
    resizeFrame = requestAnimationFrame(() => {cy.resize(); cy.fit(undefined, 35);});
  });
  observer.observe($("cy"));
  cy.on("tap", "node", e => inspectNode(e.target.id()).catch(error));
  cy.on("dbltap", "node", e => choose(e.target.id()).catch(error));
  cy.on("tap", "edge", e => inspectEdge(e.target.id()).catch(error));
  $("fit").addEventListener("click", () => cy.fit(undefined, 35));
  for (const id of ["status", "depth", "mentions", "relation"]) $(id).addEventListener("change", () => refreshGraph().catch(error));
  let timer;
  $("search").addEventListener("input", () => {clearTimeout(timer); timer = setTimeout(() => search().catch(error), 180);});
  $("kind").addEventListener("change", () => search().catch(error));
  $("more").addEventListener("click", () => search(true).catch(error));
  const meta = await api("meta");
  $("snapshot").textContent = meta.entry_count + " entries · " + meta.state_sha256.slice(0, 10) + (meta.source_watch ? " · source checked" : " · historical snapshot");
  $("snapshot").title = "Source state: " + meta.state_sha256;
  $("version").textContent = cytoscape.version;
  for (const k of meta.kinds) {const option = element("option", label(k.kind) + " (" + k.count + ")"); option.value = k.kind; $("kind").append(option);}
  for (const r of meta.relations) {const option = element("option", label(r)); option.value = r; $("relation").append(option);}
  await search();
  const first = meta.hubs.find(n => n.kind === "project") || meta.hubs[0];
  if (first) await choose(first.id);
  else $("notice").textContent = "No confirmed entities yet. Search for an entry to inspect its recorded or proposed links.";
}
start().catch(error);
