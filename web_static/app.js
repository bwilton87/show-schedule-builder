const state = {
  allRiders: [],
  selectedRiders: [],
  classMap: {},
  rideCounts: {},
};

const elements = {
  showName: document.querySelector("#showName"),
  sourceType: document.querySelector("#sourceType"),
  rideUrl: document.querySelector("#rideUrl"),
  arenaSourceFields: document.querySelector("#arenaSourceFields"),
  rideScheduleUrl: document.querySelector("#rideScheduleUrl"),
  urlHelp: document.querySelector("#urlHelp"),
  statusText: document.querySelector("#statusText"),
  loadRidersButton: document.querySelector("#loadRidersButton"),
  riderSearch: document.querySelector("#riderSearch"),
  addSelectedButton: document.querySelector("#addSelectedButton"),
  removeSelectedButton: document.querySelector("#removeSelectedButton"),
  availableRiders: document.querySelector("#availableRiders"),
  selectedRiders: document.querySelector("#selectedRiders"),
  loadClassesButton: document.querySelector("#loadClassesButton"),
  skipArenaSource: document.querySelector("#skipArenaSource"),
  classCount: document.querySelector("#classCount"),
  classList: document.querySelector("#classList"),
  generateButton: document.querySelector("#generateButton"),
  detailsOutput: document.querySelector("#detailsOutput"),
};

const urlHelpBySource = {
  horseshowoffice: {
    placeholder: "HorseShowOffice: https://www.horseshowoffice.com/hso/ridetimes.asp?s=5298&o=50",
    help: "From the main show page, open Ride Times Lookup and paste that URL here.",
  },
  foxvillage: {
    placeholder: "FoxVillage: https://www.foxvillage.com/show?id=11741",
    help: "Paste the FoxVillage show page URL.",
  },
  equestrianhub: {
    placeholder: "Equestrian Hub: https://equestrian-hub.com/show/274044",
    help: "Paste the Equestrian Hub show page URL.",
  },
};

function setStatus(message, isError = false) {
  elements.statusText.textContent = message;
  elements.statusText.classList.toggle("error", isError);
}

function setBusy(button, isBusy, busyText) {
  if (isBusy) {
    button.dataset.originalText = button.textContent;
    button.textContent = busyText;
    button.disabled = true;
  } else {
    button.textContent = button.dataset.originalText || button.textContent;
    button.disabled = false;
  }
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(payload),
  });
  const data = await response.json();

  if (!response.ok || !data.ok) {
    throw new Error(data.error || "Something went wrong.");
  }

  return data;
}

function selectedOptions(selectElement) {
  return Array.from(selectElement.selectedOptions).map((option) => option.value);
}

function renderAvailableRiders() {
  const search = elements.riderSearch.value.trim().toLowerCase();
  const selectedSet = new Set(state.selectedRiders);
  const riders = state.allRiders.filter((rider) => {
    return !selectedSet.has(rider) && rider.toLowerCase().includes(search);
  });

  elements.availableRiders.innerHTML = "";
  for (const rider of riders) {
    const option = new Option(rider, rider);
    elements.availableRiders.add(option);
  }
}

function selectedRiderLabel(rider) {
  const count = state.rideCounts[rider];

  if (count === undefined) {
    return rider;
  }

  return `${rider} (${count} ride${count === 1 ? "" : "s"})`;
}

function renderSelectedRiders() {
  elements.selectedRiders.innerHTML = "";

  for (const rider of [...state.selectedRiders].sort((a, b) => a.localeCompare(b))) {
    const option = new Option(selectedRiderLabel(rider), rider);
    elements.selectedRiders.add(option);
  }
}

function renderRiders() {
  renderAvailableRiders();
  renderSelectedRiders();
  updateGenerateState();
}

function renderClasses() {
  const entries = Object.entries(state.classMap).sort(([a], [b]) => {
    return a.localeCompare(b, undefined, {numeric: true});
  });

  elements.classCount.textContent = entries.length;
  elements.classList.innerHTML = "";

  if (!entries.length) {
    elements.classList.innerHTML = '<div class="class-row"><span class="class-code">None</span><span>Load classes after selecting riders.</span></div>';
    updateGenerateState();
    return;
  }

  for (const [code, name] of entries) {
    const row = document.createElement("div");
    row.className = "class-row";
    row.innerHTML = `<span class="class-code"></span><span></span>`;
    row.children[0].textContent = code;
    row.children[1].textContent = name;
    elements.classList.append(row);
  }

  updateGenerateState();
}

function updateGenerateState() {
  const arenaReady = (
    elements.sourceType.value !== "horseshowoffice"
    || elements.skipArenaSource.checked
    || elements.rideScheduleUrl.value.trim()
  );
  const ready = Boolean(
    elements.showName.value.trim()
    && state.selectedRiders.length
    && Object.keys(state.classMap).length
    && arenaReady
  );
  elements.generateButton.disabled = !ready;
}

function updateSourceGuidance() {
  const guidance = urlHelpBySource[elements.sourceType.value];
  elements.rideUrl.placeholder = guidance.placeholder;
  elements.urlHelp.textContent = guidance.help;
  elements.arenaSourceFields.hidden = elements.sourceType.value !== "horseshowoffice";
  updateGenerateState();
}

function downloadGeneratedExcel(downloadUrl) {
  const downloadLink = document.createElement("a");
  downloadLink.href = downloadUrl;
  downloadLink.download = "";
  document.body.append(downloadLink);
  downloadLink.click();
  downloadLink.remove();
}

function addSelectedRiders() {
  const riders = selectedOptions(elements.availableRiders);
  const selectedSet = new Set(state.selectedRiders);

  for (const rider of riders) {
    selectedSet.add(rider);
  }

  state.selectedRiders = Array.from(selectedSet);
  state.classMap = {};
  renderRiders();
  renderClasses();
}

function removeSelectedRiders() {
  const ridersToRemove = new Set(selectedOptions(elements.selectedRiders));
  state.selectedRiders = state.selectedRiders.filter((rider) => {
    return !ridersToRemove.has(rider);
  });
  state.classMap = {};
  renderRiders();
  renderClasses();
}

async function loadRiders() {
  setBusy(elements.loadRidersButton, true, "Loading...");
  setStatus("Loading riders from show URL...");
  elements.detailsOutput.textContent = "";

  try {
    const data = await postJson("/api/load-riders", {
      showName: elements.showName.value,
      sourceType: elements.sourceType.value,
      rideUrl: elements.rideUrl.value,
    });

    state.allRiders = data.riders;
    state.selectedRiders = [];
    state.classMap = {};
    state.rideCounts = {};
    renderRiders();
    renderClasses();
    setStatus(`Loaded ${data.riderCount} riders. Select riders for the schedule.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(elements.loadRidersButton, false);
  }
}

async function loadClasses() {
  setBusy(elements.loadClassesButton, true, "Loading...");
  setStatus("Loading rides and class definitions for selected riders...");

  try {
    const data = await postJson("/api/load-classes", {
      riders: state.selectedRiders,
    });

    state.classMap = data.classMap;
    state.rideCounts = data.rideCounts;
    renderRiders();
    renderClasses();
    setStatus(`Loaded ${data.classCount} class definitions from ${data.rideCount} rides.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(elements.loadClassesButton, false);
  }
}

async function generateSchedule() {
  setBusy(elements.generateButton, true, "Generating...");
  setStatus("Generating Excel schedule...");

  try {
    const data = await postJson("/api/generate", {
      showName: elements.showName.value,
      riders: state.selectedRiders,
      sourceType: elements.sourceType.value,
      rideScheduleUrl: elements.rideScheduleUrl.value,
      skipArenaSource: elements.skipArenaSource.checked,
    });

    elements.detailsOutput.textContent = data.details;
    downloadGeneratedExcel(data.downloadUrl);
    setStatus(`Generated ${data.excelFilename} from ${data.rideCount} rides.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    setBusy(elements.generateButton, false);
    updateGenerateState();
  }
}

elements.sourceType.addEventListener("change", updateSourceGuidance);
elements.showName.addEventListener("input", updateGenerateState);
elements.rideScheduleUrl.addEventListener("input", updateGenerateState);
elements.skipArenaSource.addEventListener("change", updateGenerateState);
elements.riderSearch.addEventListener("input", renderAvailableRiders);
elements.loadRidersButton.addEventListener("click", loadRiders);
elements.addSelectedButton.addEventListener("click", addSelectedRiders);
elements.removeSelectedButton.addEventListener("click", removeSelectedRiders);
elements.loadClassesButton.addEventListener("click", loadClasses);
elements.generateButton.addEventListener("click", generateSchedule);
elements.availableRiders.addEventListener("dblclick", addSelectedRiders);
elements.selectedRiders.addEventListener("dblclick", removeSelectedRiders);

updateSourceGuidance();
renderClasses();
