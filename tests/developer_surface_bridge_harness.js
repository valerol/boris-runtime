const fs = require("fs");
const vm = require("vm");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

class FakeClassList {
  constructor() {
    this.values = new Set();
  }

  add(...values) {
    for (const value of values) this.values.add(value);
  }

  remove(...values) {
    for (const value of values) this.values.delete(value);
  }

  toggle(value, force) {
    const enabled = force === undefined ? !this.values.has(value) : force;
    if (enabled) this.values.add(value);
    else this.values.delete(value);
    return enabled;
  }

  contains(value) {
    return this.values.has(value);
  }
}

class FakeElement {
  constructor(tagName = "div", id = "") {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.listeners = new Map();
    this.classList = new FakeClassList();
    this.dataset = {};
    this.value = "";
    this.textContent = "";
    this.disabled = false;
    this.checked = false;
    this.type = "";
    this.title = "";
    this.placeholder = "";
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = [...children];
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  async dispatch(type) {
    for (const listener of this.listeners.get(type) || []) {
      await listener({ type, target: this });
    }
  }

  querySelectorAll(selector) {
    const matches = [];
    const visit = (node) => {
      if (!(node instanceof FakeElement)) return;
      const isCheckbox = (
        node.tagName === "INPUT"
        && node.type === "checkbox"
      );
      if (
        (selector === "input[type=checkbox]" && isCheckbox)
        || (
          selector === "input[type=checkbox]:checked"
          && isCheckbox
          && node.checked
        )
      ) {
        matches.push(node);
      }
      for (const child of node.children) visit(child);
    };
    visit(this);
    return matches;
  }
}

class FakeOption extends FakeElement {
  constructor(text, value, defaultSelected = false, selected = false) {
    super("option");
    this.textContent = text;
    this.value = value;
    this.defaultSelected = defaultSelected;
    this.selected = selected;
  }
}

async function main() {
  const htmlPath = process.argv[2];
  const html = fs.readFileSync(htmlPath, "utf8");
  const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
  assert(scriptMatch, "Developer Surface script was not found.");

  const elements = new Map();
  const document = {
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, new FakeElement("div", id));
      }
      return elements.get(id);
    },
    createElement(tagName) {
      return new FakeElement(tagName);
    },
  };

  const messageListeners = [];
  const requestMethods = [];
  const requestSequence = [];
  let rejectStandardMessage = false;
  let aliasCalls = 0;

  const calculationOrder = {
    structuredContent: {
      work_order_version: "boris-semantic-work-order/0.5",
      work_order_id: "calculation-1",
      work_order_type: "CALCULATION",
      session_id: "surface-session",
      resume_count: 1,
      status: "semantic_work_order",
      semantic_provider: "CHATGPT_HOST_ONLY",
      phase: "C00",
      minimum_context_window_tokens: 524288,
      core_ref: {},
      issued_at: "2026-07-27T10:00:00+00:00",
      expires_at: "2026-07-27T10:15:00+00:00",
      response_schema: { type: "object" },
      bindings: {},
      limitations: [],
      submission_contract: {
        tool: "boris.execute",
        required_arguments: [
          "work_order_id",
          "work_order_token",
          "semantic_result",
        ],
        work_order_token: "hw1.payload.signature",
      },
    },
  };

  const parent = {
    postMessage(message) {
      if (message.id === undefined) return;
      requestMethods.push(message.method);
      requestSequence.push(message.method);
      queueMicrotask(() => {
        let response;
        if (message.method === "tools/call") {
          response = {
            jsonrpc: "2.0",
            id: message.id,
            result: calculationOrder,
          };
        } else if (
          message.method === "ui/message"
          && rejectStandardMessage
        ) {
          response = {
            jsonrpc: "2.0",
            id: message.id,
            error: { message: "ui/message unavailable" },
          };
        } else {
          response = {
            jsonrpc: "2.0",
            id: message.id,
            result: {},
          };
        }
        for (const listener of messageListeners) {
          listener({ source: parent, data: response });
        }
      });
    },
  };

  const window = {
    parent,
    openai: {
      toolResponseMetadata: {},
      async sendFollowUpMessage() {
        aliasCalls += 1;
        requestSequence.push("sendFollowUpMessage");
      },
    },
    addEventListener(type, listener) {
      if (type === "message") messageListeners.push(listener);
    },
    setTimeout() {
      return 1;
    },
  };

  vm.runInNewContext(scriptMatch[1], {
    window,
    document,
    Option: FakeOption,
    Map,
    Set,
    JSON,
    Object,
    Array,
    String,
    Error,
    console,
  });
  await Promise.resolve();
  await Promise.resolve();

  const holdPayload = {
    structuredContent: {
      execution_version: "boris-execution/1.0",
      session_id: "surface-session",
      status: "semantic_candidate",
      phase: "C00",
      gate: "HOLD",
      candidate_result: null,
      norm_results: [],
      unknowns: [],
      conflicts: [],
      alternatives: [],
      limitations: [],
      hold: {
        status: "operator_input_required",
        continuation_token: "v1.payload.signature",
        resume_count: 0,
        hold_record: {
          hold_id: "hold-1",
          state_hash: "a".repeat(64),
        },
        required_operator_input: {
          question: "Choose a continuation.",
          resolution_modes: [{
            mode: "ALLOW_CONDITIONAL_PROCEEDING",
            available: true,
            effect: "Preserve unknowns.",
          }],
          semantic_unknowns: [],
          predicate_inputs: [],
          system_targets: [],
        },
      },
    },
  };
  for (const listener of messageListeners) {
    listener({
      source: parent,
      data: {
        jsonrpc: "2.0",
        method: "ui/notifications/tool-result",
        params: holdPayload,
      },
    });
  }

  document.getElementById("resolution-mode").value = (
    "ALLOW_CONDITIONAL_PROCEEDING"
  );
  document.getElementById("operator-statement").value = (
    "Preserve every unknown and recalculate conditionally."
  );
  await document.getElementById("resume-button").dispatch("click");

  const status = document.getElementById("host-wake-status").textContent;
  const detail = document.getElementById("host-wake-detail").textContent;
  assert(
    document.getElementById("resume-value").textContent === "1",
    "The top-level work-order resume_count was not rendered."
  );
  assert(
    status.includes("not yet confirmed"),
    "The UI claimed more than a wake-up request acknowledgement."
  );
  assert(
    detail.includes("ui/message"),
    "The standards-first ui/message transport was not reported."
  );
  assert(
    aliasCalls === 0,
    "The compatibility alias ran despite successful ui/message."
  );
  assert(
    !document.getElementById("host-wake-panel").classList.contains("hidden"),
    "The manual host wake-up control is hidden."
  );

  const initialMessages = requestMethods.filter(
    (method) => method === "ui/message"
  ).length;
  await document.getElementById("host-wake-button").dispatch("click");
  assert(
    requestMethods.filter((method) => method === "ui/message").length
      === initialMessages + 1,
    "Manual host wake-up did not repeat ui/message."
  );

  rejectStandardMessage = true;
  const sequenceStart = requestSequence.length;
  await document.getElementById("host-wake-button").dispatch("click");
  const fallbackSequence = requestSequence.slice(sequenceStart);
  assert(
    fallbackSequence[0] === "ui/update-model-context"
      && fallbackSequence[1] === "ui/message"
      && fallbackSequence[2] === "sendFollowUpMessage",
    "The ChatGPT alias did not run strictly after ui/message failed."
  );
  assert(aliasCalls === 1, "The compatibility alias fallback did not run.");
}

main().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
