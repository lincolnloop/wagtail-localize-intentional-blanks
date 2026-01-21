/**
 * Translation Editor Enhancements for Intentional Blanks
 *
 * Adds "Do Not Translate" buttons to wagtail-localize's translation editor.
 */

(function () {
  "use strict";

  // Configuration (can be overridden by Django template)
  const config = {
    apiBaseUrl: window.INTENTIONAL_BLANKS_API_URL || "/intentional-blanks/",
    labelText: "Mark 'Do Not Translate'",
    marker: "__DO_NOT_TRANSLATE__",
    backupSeparator: "|backup|",
    cssClasses: {
      container: "do-not-translate",
      checkboxContainer: "do-not-translate-checkbox-container",
      checkbox: "do-not-translate-checkbox",
      label: "do-not-translate-label",
    },
    bulkActions: {
      modes: {
        mark: "mark",
        unmark: "unmark",
      },
      buttonText: {
        markAll: "Mark All 'Do Not Translate'",
        unmarkAll: "Unmark All 'Do Not Translate'",
        marking: "Marking...",
        unmarking: "Unmarking...",
      },
    },
  };

  /**
   * Clean props data before React initializes.
   * Replaces marker strings with actual values so React never sees the marker.
   */
  function cleanPropsData() {
    const editorContainer = document.querySelector(".js-translation-editor");
    if (!editorContainer) {
      return false;
    }

    if (!editorContainer.dataset.props) {
      return false;
    }

    try {
      const props = JSON.parse(editorContainer.dataset.props);

      if (!props.segments) {
        return;
      }

      if (!props.initialStringTranslations) {
        return;
      }

      // Build a map: StringSegment ID → source value
      // This matches how wagtail-localize links translations to segments
      const segmentMap = new Map();
      props.segments.forEach((segment) => {
        if (segment.type === "string") {
          // segment.id is the StringSegment ID (primary key)
          segmentMap.set(segment.id, segment.source);
        }
      });

      let cleanedCount = 0;
      props.initialStringTranslations.forEach((translation, index) => {
        if (!translation.data) return;

        const isMarker = translation.data === config.marker;
        const hasBackup = translation.data.startsWith(
          config.marker + config.backupSeparator,
        );

        if (isMarker || hasBackup) {
          if (hasBackup) {
            // Extract original value from backup
            const parts = translation.data.split(config.backupSeparator);
            if (parts.length > 1) {
              translation.data = parts[1];
            }
          } else {
            // No backup, use source value from segment
            // Use segment_id (not string_id) to look up the source value
            const sourceValue = segmentMap.get(translation.segment_id);
            translation.data = sourceValue || "";
          }

          // Clear translation metadata to prevent "Translated manually on..." text
          translation.last_translated_by = null;
          translation.comment = "";

          cleanedCount++;
        }
      });

      // Write cleaned data back
      editorContainer.dataset.props = JSON.stringify(props);

      return true;
    } catch (e) {
      return false;
    }
  }

  // CRITICAL: Clean props as early as possible, before React initializes
  let propsAlreadyCleaned = false;

  // Try immediately (synchronous)
  if (cleanPropsData()) {
    propsAlreadyCleaned = true;
  } else {
    // Container doesn't exist yet - watch for it to appear

    const observer = new MutationObserver(() => {
      const editorContainer = document.querySelector(".js-translation-editor");
      if (
        editorContainer &&
        editorContainer.dataset.props &&
        !propsAlreadyCleaned
      ) {
        if (cleanPropsData()) {
          propsAlreadyCleaned = true;
          observer.disconnect();
        }
      }
    });

    // Watch for container to be added to DOM
    if (document.documentElement) {
      observer.observe(document.documentElement, {
        childList: true,
        subtree: true,
      });
    }
  }

  /**
   * Update props JSON after marking/unmarking a segment.
   * Keeps React's data in sync with the backend.
   */
  function updatePropsAfterToggle(
    segmentId,
    doNotTranslate,
    sourceValue,
    translatedValue,
  ) {
    const editorContainer = document.querySelector(".js-translation-editor");
    if (!editorContainer || !editorContainer.dataset.props) {
      return;
    }

    try {
      const props = JSON.parse(editorContainer.dataset.props);

      // Find the translation in initialStringTranslations by segment_id
      // segmentId here is the StringSegment ID
      const translation = props.initialStringTranslations?.find(
        (t) => t.segment_id === segmentId,
      );

      if (translation) {
        if (doNotTranslate) {
          // Marking - use source value and clear metadata
          translation.data = sourceValue;
          translation.last_translated_by = null;
          translation.comment = "";
        } else {
          // Unmarking - use translated value or empty
          translation.data = translatedValue || "";
          // Metadata will be restored when user edits/saves the translation
        }

        editorContainer.dataset.props = JSON.stringify(props);
      } else {
      }
    } catch (e) {
      console.error("[updatePropsAfterToggle] Error updating props:", e);
    }
  }

  /**
   * Initialize everything in the correct order
   */
  function init() {
    function initAll() {
      // Try to clean props if not already done
      if (!propsAlreadyCleaned) {
        if (cleanPropsData()) {
          propsAlreadyCleaned = true;
        }
      } else {
      }
      // Initialize our UI enhancements
      initializeButtons();
    }

    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", initAll);
    } else {
      // DOM already ready, run immediately
      initAll();
    }
  }

  // Track if buttons have been initialized to prevent duplicates
  let buttonsInitialized = false;

  /**
   * Add "Do Not Translate" checkboxes to all translation segments
   */
  function initializeButtons() {
    if (buttonsInitialized) {
      return;
    }

    const editorContainer = document.querySelector(".js-translation-editor");
    if (!editorContainer) {
      return;
    }

    let segmentsData;
    try {
      const propsData = JSON.parse(editorContainer.dataset.props);
      segmentsData = (propsData.segments || []).filter(
        (seg) => seg.type === "string",
      );
    } catch (e) {
      console.error("Failed to parse translation editor data:", e);
      return;
    }

    if (segmentsData.length === 0) {
      return;
    }

    // Wait for React to render segments
    const observer = new MutationObserver(() => {
      const segmentElements = document.querySelectorAll(
        "li.incomplete, li.complete",
      );

      if (
        segmentElements.length > 0 &&
        segmentElements.length === segmentsData.length &&
        !buttonsInitialized
      ) {
        observer.disconnect();
        buttonsInitialized = true;
        attachButtonsToSegments(segmentElements, segmentsData);
      }
    });

    observer.observe(document.body, { childList: true, subtree: true });

    // Fallback if React has already rendered
    setTimeout(() => {
      if (!buttonsInitialized) {
        const segmentElements = document.querySelectorAll(
          "li.incomplete, li.complete",
        );
        if (segmentElements.length === segmentsData.length) {
          observer.disconnect();
          buttonsInitialized = true;
          attachButtonsToSegments(segmentElements, segmentsData);
        } else {
        }
      }
    }, 1000);
  }

  /**
   * Attach checkboxes to rendered segment elements
   */
  function attachButtonsToSegments(segmentElements, segmentsData) {
    const translationId = getTranslationId();
    if (!translationId) {
      return;
    }

    segmentElements.forEach((container, index) => {
      if (index >= segmentsData.length) return;

      const segmentData = segmentsData[index];

      // Use segment.id (StringSegment ID) - matches wagtail-localize's structure
      // This is what the backend expects and what links to translations
      const segmentId = segmentData.id;

      if (!segmentId) return;

      container.dataset.segmentId = segmentId;

      const buttonContainer = container.querySelector("ul");
      if (!buttonContainer) {
        return;
      }

      const checkboxWrapper = createDoNotTranslateCheckbox(
        segmentId,
        translationId,
      );
      const listItem = document.createElement("li");
      listItem.appendChild(checkboxWrapper);

      // Always insert as the last child to maintain consistent position
      // Mark it so we can identify it later
      listItem.dataset.intentionalBlanksCheckbox = "true";
      buttonContainer.appendChild(listItem);

      setupEditModeObserver(container, listItem);
    });

    checkAllSegmentsStatus(translationId);

    // Insert bulk action button after checkboxes are initialized
    insertBulkActionButton();
  }

  /**
   * Create a checkbox with label for "Do Not Translate"
   */
  function createDoNotTranslateCheckbox(segmentId, translationId) {
    // Create container
    const container = document.createElement("div");
    container.className = config.cssClasses.checkboxContainer;

    // Create checkbox
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.id = `do-not-translate-${segmentId}`;
    checkbox.className = config.cssClasses.checkbox;
    checkbox.dataset.translationId = translationId;

    // Create label
    const label = document.createElement("label");
    label.htmlFor = checkbox.id;
    label.className = config.cssClasses.label;
    label.textContent = config.labelText;

    // Add change event listener
    checkbox.addEventListener("change", function (e) {
      toggleDoNotTranslate(checkbox, segmentId, translationId);
    });

    // Append checkbox and label to container
    container.appendChild(checkbox);
    container.appendChild(label);

    return container;
  }

  /**
   * Toggle "do not translate" status for a segment
   */
  function toggleDoNotTranslate(checkbox, segmentId, translationId) {
    const container = checkbox.closest("[data-segment-id]");

    if (!container) {
      console.error("Container not found for segment", segmentId);
      return;
    }

    const doNotTranslate = checkbox.checked;

    // Disable checkbox during request
    checkbox.disabled = true;

    const url = `${config.apiBaseUrl}translations/${translationId}/segment/${segmentId}/do-not-translate/`;
    const formData = new FormData();
    formData.append("do_not_translate", doNotTranslate);
    formData.append("csrfmiddlewaretoken", getCsrfToken());

    fetch(url, {
      method: "POST",
      body: formData,
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          // Update React's props data first
          updatePropsAfterToggle(
            segmentId,
            data.do_not_translate,
            data.source_value,
            data.translated_value,
          );

          // Then update the UI
          updateSegmentUI(
            container,
            checkbox,
            data.do_not_translate,
            data.source_value,
            data.translated_value,
          );
          showNotification("success", data.message);

          // Update bulk button state
          updateBulkButtonState();
        } else {
          // Revert checkbox state on error
          checkbox.checked = !doNotTranslate;
          showNotification("error", data.error || "Failed to update segment");
        }
      })
      .catch((error) => {
        console.error("Error toggling do not translate:", error);
        // Revert checkbox state on error
        checkbox.checked = !doNotTranslate;
        showNotification("error", "Network error occurred");
      })
      .finally(() => {
        checkbox.disabled = false;
      });
  }

  /**
   * Check the status of all segments with a single API call
   */
  function checkAllSegmentsStatus(translationId) {
    const url = `${config.apiBaseUrl}translations/${translationId}/status/?t=${Date.now()}`;

    fetch(url, { cache: "no-store" }) // Do not cache the API call
      .then((response) => response.json())
      .then((data) => {
        if (data.success && data.segments) {
          Object.keys(data.segments).forEach((segmentId) => {
            const segmentData = data.segments[segmentId];
            const container = document.querySelector(
              `[data-segment-id="${segmentId}"]`,
            );

            if (container && segmentData.do_not_translate) {
              const checkbox = container.querySelector(
                `.${config.cssClasses.checkbox}`,
              );
              if (checkbox) {
                updateSegmentUI(
                  container,
                  checkbox,
                  true,
                  segmentData.source_text,
                );
              }
            }
          });

          // Update bulk button state after loading initial states
          updateBulkButtonState();
        }
      })
      .catch((error) =>
        console.error("Error checking segments status:", error),
      );
  }

  /**
   * Set up observer to show/hide checkbox based on edit mode
   */
  function setupEditModeObserver(container, checkboxContainer) {
    const observer = new MutationObserver(() => {
      const textarea = container.querySelector("textarea");
      const isEditMode = !!textarea;

      // Hide checkbox in edit mode, show when not editing
      if (checkboxContainer) {
        checkboxContainer.style.display = isEditMode ? "none" : "";
      }

      // Ensure checkbox stays at the end of the button list
      // React may re-render buttons and insert them before our checkbox
      const buttonContainer = container.querySelector("ul");
      if (
        buttonContainer &&
        checkboxContainer &&
        checkboxContainer.parentNode === buttonContainer
      ) {
        // Check if checkbox is already the last child
        if (buttonContainer.lastElementChild !== checkboxContainer) {
          // Move it to the end
          buttonContainer.appendChild(checkboxContainer);
        }
      }

      // If textarea appears and we have a restored value, apply it
      if (textarea && container.dataset.restoredValue) {
        textarea.value = container.dataset.restoredValue;
        delete container.dataset.restoredValue;
      }
    });

    // Observe for edit mode changes
    observer.observe(container, {
      childList: true,
      subtree: true,
    });

    // Store observer
    container._editModeObserver = observer;

    // Set initial state
    const textarea = container.querySelector("textarea");
    if (checkboxContainer && textarea) {
      checkboxContainer.style.display = "none";
    }
  }

  /**
   * Hide/show the Edit button based on marked state
   */
  function toggleEditButton(container, hide) {
    // Find the "Translate" or "Edit" button - it's usually a button with specific text
    const buttons = container.querySelectorAll("button");
    buttons.forEach((button) => {
      const buttonText = button.textContent.trim();
      if (buttonText === "Translate" || buttonText === "Edit") {
        button.style.display = hide ? "none" : "";
      }
    });
  }

  /**
   * Add "Using source value" badge after field name
   */
  function addDoNotTranslateBadge(container) {
    // Check if badge already exists
    if (container.querySelector(".do-not-translate-badge")) return;

    // Create badge element
    const badge = document.createElement("span");
    badge.className = "do-not-translate-badge";
    badge.textContent = "Using source value";

    // Try to find the field name (h4 element) and append badge to it
    const fieldName = container.querySelector("h4");
    if (fieldName) {
      fieldName.appendChild(badge);
      return;
    }

    // Fallback: if no h4, insert before the p element
    const paragraph = container.querySelector("p");
    if (paragraph) {
      paragraph.parentNode.insertBefore(badge, paragraph);
    }
  }

  /**
   * Remove "Using source value" badge
   */
  function removeDoNotTranslateBadge(container) {
    const badge = container.querySelector(".do-not-translate-badge");
    if (badge) {
      badge.remove();
    }
  }

  /**
   * Update the UI to reflect segment status
   */
  function updateSegmentUI(
    container,
    checkbox,
    doNotTranslate,
    sourceValue,
    translatedValue,
  ) {
    if (!container) return;

    // Find the editable field (textarea) or the display element (p tag in non-editable state)
    const textarea = container.querySelector("textarea");
    const displayP = container.querySelector("div.sc-iCoGMd p");

    // Update checkbox state
    checkbox.checked = doNotTranslate;

    if (doNotTranslate) {
      // Mark as do not translate - show source value
      container.classList.add(config.cssClasses.container);

      // Update wagtail-localize status classes
      container.classList.remove("incomplete");
      container.classList.add("complete");

      // Update textarea if in editable state
      if (textarea) {
        textarea.value = sourceValue;
        textarea.readOnly = true;
        textarea.style.opacity = "0.7";
        textarea.style.backgroundColor = "#f5f5f5";
      }

      // Update display paragraph if in non-editable state
      if (displayP) {
        displayP.textContent = sourceValue;
      }

      // Add badge after field name
      addDoNotTranslateBadge(container);

      // Hide the Edit button when marked as "Do Not Translate"
      toggleEditButton(container, true);
    } else {
      // Unmark - restore translated value or clear to allow editing
      container.classList.remove(config.cssClasses.container);

      // Update wagtail-localize status classes based on whether there's a translation
      if (translatedValue !== null && translatedValue !== undefined) {
        container.classList.remove("incomplete");
        container.classList.add("complete");
      } else {
        container.classList.remove("complete");
        container.classList.add("incomplete");
      }

      // Restore textarea if in editable state
      if (textarea) {
        if (translatedValue !== null && translatedValue !== undefined) {
          textarea.value = translatedValue;
        } else {
          // No translation - clear the textarea
          textarea.value = "";
        }
        textarea.readOnly = false;
        textarea.style.opacity = "1";
        textarea.style.backgroundColor = "";
      }

      // Restore display paragraph if in non-editable state
      if (displayP) {
        if (translatedValue !== null && translatedValue !== undefined) {
          displayP.textContent = translatedValue;
          // Store value for when user clicks Edit (React will create textarea with stale data)
          container.dataset.restoredValue = translatedValue;
        } else {
          // No translation - clear the display and store empty string
          displayP.textContent = "";
          // Store empty string to override React's stale data
          container.dataset.restoredValue = "";
        }
      }

      // Remove badge
      removeDoNotTranslateBadge(container);

      // Show the Edit button when unmarked
      toggleEditButton(container, false);
    }
  }

  /**
   * Get translation ID from page context
   */
  function getTranslationId() {
    // Try multiple methods to find translation ID

    // 1. From URL
    const match = window.location.pathname.match(/\/translations\/(\d+)\//);
    if (match) return match[1];

    // 2. From data attribute
    const editor = document.querySelector("[data-translation-id]");
    if (editor) return editor.dataset.translationId;

    // 3. From global variable (set by Django template)
    if (window.TRANSLATION_ID) return window.TRANSLATION_ID;

    return null;
  }

  /**
   * Get CSRF token from page
   */
  function getCsrfToken() {
    const input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input) return input.value;

    const cookie = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));
    if (cookie) return cookie.split("=")[1];

    return "";
  }

  /**
   * Show a notification message
   */
  function showNotification(type, message) {
    // Try to use Wagtail's notification system
    if (window.wagtail && window.wagtail.messages) {
      window.wagtail.messages.add({
        type: type,
        text: message,
      });
    } else if (window.messages && window.messages.add) {
      // Older Wagtail versions
      window.messages.add(message, type);
    } else {
      // Fallback to console
      console.log(`[${type.toUpperCase()}] ${message}`);
    }
  }

  // Track if bulk button has been inserted
  let bulkButtonInserted = false;
  let bulkButton = null;

  /**
   * Update bulk button text while preserving the icon
   */
  function updateBulkButtonText(button, text) {
    // Find and update only the text node, preserving the icon
    for (let i = 0; i < button.childNodes.length; i++) {
      if (button.childNodes[i].nodeType === Node.TEXT_NODE) {
        button.childNodes[i].textContent = text;
        return;
      }
    }
  }

  /**
   * Get current bulk button text (without icon)
   */
  function getBulkButtonText(button) {
    for (let i = 0; i < button.childNodes.length; i++) {
      if (button.childNodes[i].nodeType === Node.TEXT_NODE) {
        return button.childNodes[i].textContent;
      }
    }
    return "";
  }

  /**
   * Create the bulk action button element
   */
  function createBulkActionButton() {
    // Create container
    const container = document.createElement("div");
    container.className =
      "intentional-blanks-bulk-action-container w-tabs__panel";

    // Create button
    const button = document.createElement("button");
    // button.className = "intentional-blanks-bulk-button";
    button.className =
      "button button-primary button--icon intentional-blanks-bulk-button";
    button.type = "button";
    button.dataset.mode = config.bulkActions.modes.mark;

    // Create icon
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("class", "icon icon-wagtail-localize-language");
    icon.setAttribute("aria-hidden", "true");

    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", "#icon-wagtail-localize-language");

    icon.appendChild(use);
    button.appendChild(icon);

    // Add text content after icon
    button.appendChild(
      document.createTextNode(config.bulkActions.buttonText.markAll),
    );

    // Add click event
    button.addEventListener("click", handleBulkActionClick);

    const paragraph = document.createElement("p");
    paragraph.textContent = "Mark All fields as 'Do Not Translate'";

    container.appendChild(paragraph);
    container.appendChild(button);
    bulkButton = button;

    return container;
  }

  /**
   * Insert bulk action button inside the first child of tab-content
   */
  function insertBulkActionButton() {
    if (bulkButtonInserted) {
      return;
    }

    // Find the section with id="tab-content" and class="active"
    // (There are two sections with id="tab-content", we want the inner one)
    const tabContent = document.querySelector("section#tab-content.active");
    if (!tabContent) {
      return;
    }

    // Find the container that holds the w-tabs__panel elements
    const toolboxContainer = Array.from(tabContent.children).find((child) => {
      return child.querySelector(".w-tabs__panel") !== null;
    });

    if (!toolboxContainer) {
      return;
    }

    // Create the button container
    const buttonContainer = createBulkActionButton();

    // Append as the last child of the toolbox container
    toolboxContainer.appendChild(buttonContainer);

    bulkButtonInserted = true;

    // Initial state update
    updateBulkButtonState();
  }

  /**
   * Update bulk button state based on checkbox states
   */
  function updateBulkButtonState() {
    if (!bulkButton) {
      return;
    }

    const checkboxes = document.querySelectorAll(
      "." + config.cssClasses.checkbox,
    );
    const totalCheckboxes = checkboxes.length;

    if (totalCheckboxes === 0) {
      // No checkboxes - disable button
      bulkButton.disabled = true;
      return;
    }

    const checkedCheckboxes = Array.from(checkboxes).filter(
      (cb) => cb.checked,
    ).length;

    if (checkedCheckboxes === totalCheckboxes) {
      // All checked - show "Unmark All"
      updateBulkButtonText(bulkButton, config.bulkActions.buttonText.unmarkAll);
      bulkButton.dataset.mode = config.bulkActions.modes.unmark;
    } else {
      // At least one unchecked - show "Mark All"
      updateBulkButtonText(bulkButton, config.bulkActions.buttonText.markAll);
      bulkButton.dataset.mode = config.bulkActions.modes.mark;
    }

    bulkButton.disabled = false;
  }

  /**
   * Handle bulk action button click
   */
  function handleBulkActionClick() {
    if (!bulkButton) {
      return;
    }

    const mode = bulkButton.dataset.mode;

    // Disable button during operation
    bulkButton.disabled = true;
    const originalText = getBulkButtonText(bulkButton);
    updateBulkButtonText(
      bulkButton,
      mode === config.bulkActions.modes.mark
        ? config.bulkActions.buttonText.marking
        : config.bulkActions.buttonText.unmarking,
    );

    const operation =
      mode === config.bulkActions.modes.mark
        ? markAllSegments()
        : unmarkAllSegments();

    operation
      .then(() => {
        // Success - button state will be updated by updateBulkButtonState
        updateBulkButtonState();
      })
      .catch((error) => {
        // Error - restore button
        console.error("Bulk action failed:", error);
        updateBulkButtonText(bulkButton, originalText);
        bulkButton.disabled = false;
      });
  }

  /**
   * Mark all segments as "do not translate"
   */
  function markAllSegments() {
    const translationId = getTranslationId();
    if (!translationId) {
      return Promise.reject(new Error("Translation ID not found"));
    }

    const url = `${config.apiBaseUrl}translations/${translationId}/toggle-all-do-not-translate/`;
    const formData = new FormData();
    formData.append("do_not_translate", "true");
    formData.append("csrfmiddlewaretoken", getCsrfToken());

    return fetch(url, {
      method: "POST",
      body: formData,
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          // Update all checkboxes and UI
          data.segment_ids.forEach((segmentId) => {
            const container = document.querySelector(
              `[data-segment-id="${segmentId}"]`,
            );
            if (container) {
              const checkbox = container.querySelector(
                "." + config.cssClasses.checkbox,
              );
              if (checkbox) {
                // Get source value from the segment
                const editorContainer = document.querySelector(
                  ".js-translation-editor",
                );
                if (editorContainer && editorContainer.dataset.props) {
                  try {
                    const props = JSON.parse(editorContainer.dataset.props);
                    const segment = props.segments.find(
                      (s) => s.id === segmentId,
                    );
                    if (segment) {
                      const sourceValue = segment.source;

                      // Update checkbox state
                      checkbox.checked = true;

                      // Update UI
                      updateSegmentUI(container, checkbox, true, sourceValue);

                      // Update props
                      updatePropsAfterToggle(
                        segmentId,
                        true,
                        sourceValue,
                        null,
                      );
                    }
                  } catch (e) {
                    console.error("Error parsing props:", e);
                  }
                }
              }
            }
          });

          showNotification("success", data.message);
        } else {
          showNotification(
            "error",
            data.error || "Failed to mark all segments",
          );
          throw new Error(data.error);
        }
      })
      .catch((error) => {
        console.error("Error marking all segments:", error);
        showNotification("error", "Network error occurred");
        throw error;
      });
  }

  /**
   * Unmark all segments
   */
  function unmarkAllSegments() {
    const translationId = getTranslationId();
    if (!translationId) {
      return Promise.reject(new Error("Translation ID not found"));
    }

    const url = `${config.apiBaseUrl}translations/${translationId}/toggle-all-do-not-translate/`;
    const formData = new FormData();
    formData.append("do_not_translate", "false");
    formData.append("csrfmiddlewaretoken", getCsrfToken());

    return fetch(url, {
      method: "POST",
      body: formData,
    })
      .then((response) => response.json())
      .then((data) => {
        if (data.success) {
          // Update all checkboxes and UI using the segment_data from backend
          const checkboxes = document.querySelectorAll(
            "." + config.cssClasses.checkbox,
          );
          checkboxes.forEach((checkbox) => {
            const container = checkbox.closest("[data-segment-id]");
            if (container) {
              const segmentId = parseInt(container.dataset.segmentId);

              // Get the actual translated value for this segment from backend response
              const segmentInfo = data.segment_data?.[segmentId];
              const translatedValue = segmentInfo?.translated_value || null;
              const sourceValue = segmentInfo?.source_value || null;

              // Uncheck checkbox
              checkbox.checked = false;

              // Update UI with the actual translated value
              updateSegmentUI(
                container,
                checkbox,
                false,
                sourceValue,
                translatedValue,
              );

              // Update props
              updatePropsAfterToggle(
                segmentId,
                false,
                sourceValue,
                translatedValue,
              );
            }
          });

          showNotification("success", data.message);
        } else {
          showNotification(
            "error",
            data.error || "Failed to unmark all segments",
          );
          throw new Error(data.error);
        }
      })
      .catch((error) => {
        console.error("Error unmarking all segments:", error);
        showNotification("error", "Network error occurred");
        throw error;
      });
  }

  // Initialize on load
  init();

  // Export for potential external use
  window.IntentionalBlanks = {
    init: init,
    config: config,
  };
})();
