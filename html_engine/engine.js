(function () {
  const data = window.statementData;
  const layout = window.statementPreciseLayout;
  const host = document.getElementById("preciseStatementPages");

  if (!data || !layout || !host) {
    return;
  }

  const PT = "pt";

  function formatAmount(value) {
    return Number(value || 0).toLocaleString("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function narrationMeasureContext() {
    if (!narrationMeasureContext.ctx) {
      const canvas = document.createElement("canvas");
      narrationMeasureContext.ctx = canvas.getContext("2d");
      const font = layout.fonts.default;
      narrationMeasureContext.ctx.font = `${font.weight} ${font.size}pt ${font.family}`;
    }

    return narrationMeasureContext.ctx;
  }

  function wrapTextToWidth(text, maxWidth) {
    const content = String(text || "").trim();

    if (!content) {
      return [];
    }

    const ctx = narrationMeasureContext();
    const lines = [];
    let start = 0;

    while (start < content.length) {
      let end = start;
      let lastBreak = -1;

      while (end < content.length) {
        const next = content.slice(start, end + 1);
        if (ctx.measureText(next).width > maxWidth) {
          break;
        }

        if (/[\s/-]/.test(content[end])) {
          lastBreak = end;
        }

        end += 1;
      }

      if (end >= content.length) {
        lines.push(content.slice(start).trim());
        break;
      }

      const breakAt = lastBreak >= start ? lastBreak + 1 : Math.max(start + 1, end);
      lines.push(content.slice(start, breakAt).trim());
      start = breakAt;

      while (start < content.length && /\s/.test(content[start])) {
        start += 1;
      }
    }

    return lines.filter(Boolean);
  }

  function parseAmount(value) {
    if (value === null || value === undefined || value === "") {
      return 0;
    }

    if (typeof value === "number") {
      return value;
    }

    return Number(String(value).replace(/,/g, "").trim()) || 0;
  }

  function normalizeTransactions(openingBalance, transactions) {
    let runningBalance = parseAmount(openingBalance);

    return transactions.map((transaction) => {
      const withdrawal = parseAmount(transaction.withdrawal);
      const deposit = parseAmount(transaction.deposit);
      runningBalance += deposit - withdrawal;

      return {
        ...transaction,
        details: Array.isArray(transaction.details) ? transaction.details.filter(Boolean) : [],
        withdrawal: withdrawal || null,
        deposit: deposit || null,
        closingBalance: runningBalance
      };
    });
  }

  function buildSummary(transactions) {
    return {
      openingBalance: parseAmount(data.openingBalance),
      debitCount: transactions.filter((transaction) => transaction.withdrawal).length,
      creditCount: transactions.filter((transaction) => transaction.deposit).length,
      debits: transactions.reduce((sum, transaction) => sum + parseAmount(transaction.withdrawal), 0),
      credits: transactions.reduce((sum, transaction) => sum + parseAmount(transaction.deposit), 0),
      closingBalance: transactions.length
        ? transactions[transactions.length - 1].closingBalance
        : parseAmount(data.openingBalance)
    };
  }

  function restoreExtractedLineBreaks(lines) {
    const restored = [];

    lines.forEach((line, index) => {
      if (!line) {
        return;
      }

      const overflowMatch = line.match(/^(.*(?:FROM|PAYMENT))([A-Z])$/);

      if (overflowMatch) {
        restored.push(overflowMatch[1]);
        restored.push(overflowMatch[2]);
        return;
      }

      restored.push(line);
    });

    return restored;
  }

  function narrationContentLines(transaction) {
    const rawLines = [transaction.narration, ...transaction.details].filter(Boolean);
    const restoredLines = restoreExtractedLineBreaks(rawLines);
    const maxWidth = layout.colBounds[2] - layout.colBounds[1] - layout.textToBorderGap * 2;

    return restoredLines.flatMap((line) => wrapTextToWidth(line, maxWidth));
  }

  function toLineItems(transactions) {
    return transactions.flatMap((transaction) => {
      const narrationLines = narrationContentLines(transaction);
      const [summaryNarration, ...detailNarration] = narrationLines;
      const items = [
        {
          type: "summary",
          date: transaction.date,
          narration: summaryNarration || "",
          reference: transaction.reference,
          valueDate: transaction.valueDate,
          withdrawal: transaction.withdrawal ? formatAmount(transaction.withdrawal) : "",
          deposit: transaction.deposit ? formatAmount(transaction.deposit) : "",
          closingBalance: formatAmount(transaction.closingBalance)
        }
      ];

      detailNarration.forEach((detail) => {
        items.push({
          type: "detail",
          text: detail
        });
      });

      return items;
    });
  }

  function splitPages(transactions) {
    const lineItems = toLineItems(transactions);
    const pages = [];
    let index = 0;
    const firstCapacity = layout.table.firstLineCapacity;
    const continuationCapacity = layout.table.continuationLineCapacity;
    const continuationCarryCapacity = Math.floor(
      (layout.footer.topY - layout.summary.carryReservedHeight - layout.table.contFirstContentY) / layout.table.lineHeight
    );

    if (lineItems.length <= firstCapacity) {
      pages.push({ lines: lineItems, showSummaryCarry: false });
      return pages;
    }

    pages.push({
      lines: lineItems.slice(index, index + firstCapacity),
      showSummaryCarry: false
    });
    index += firstCapacity;

    while (lineItems.length - index > continuationCarryCapacity) {
      const remainingAfterNext = lineItems.length - (index + continuationCapacity);
      if (remainingAfterNext <= continuationCarryCapacity) {
        break;
      }

      pages.push({
        lines: lineItems.slice(index, index + continuationCapacity),
        showSummaryCarry: false
      });
      index += continuationCapacity;
    }

    pages.push({
      lines: lineItems.slice(index),
      showSummaryCarry: true
    });

    return pages;
  }

  function branchValue(label) {
    const entry = data.branch.find((item) => item[0] === label);
    return entry ? String(entry[1] || "") : "";
  }

  function branchValueAt(index) {
    const entry = data.branch[index];
    return entry ? String(entry[1] || "") : "";
  }

  function splitName(line) {
    const normalized = String(line || "").trim().replace(/\s+/g, " ");
    const match = normalized.match(/^(MR|MS|MRS|DR)\.?\s+(.*)$/i);

    if (!match) {
      return {
        salutation: "",
        name: normalized
      };
    }

    return {
      salutation: `${match[1].toUpperCase()}.`,
      name: match[2]
    };
  }

  function splitAccountNumber(value) {
    const text = String(value || "").trim();
    const match = text.match(/^(\S+)(?:\s{2,}(.*))?$/);

    return {
      accountNumber: match ? match[1] : text,
      tail: match && match[2] ? match[2] : ""
    };
  }

  function splitIfsc(value) {
    const text = String(value || "").trim();
    const match = text.match(/^(\S+)(?:\s+(MICR\s*:?\s*.*))?$/);

    return {
      ifsc: match ? match[1] : text,
      tail: match && match[2] ? match[2] : ""
    };
  }

  function fieldValues() {
    const name = splitName(data.account.holder[0]);
    const accountNo = splitAccountNumber(branchValue("Account No"));
    const ifsc = splitIfsc(branchValue("RTGS/NEFT IFSC"));

    return {
      salutation: name.salutation,
      customer_name: name.name,
      address_line_1: data.account.holder[1],
      address_line_2: data.account.holder[2],
      city_state: data.account.holder[3],
      pin: data.account.holder[4],
      country_line: data.account.holder[5] || "",
      joint_holders_label: data.account.holder[7] || "JOINT HOLDERS :",
      nominee: data.account.nomination,
      overdraft: branchValue("OD Limit"),
      currency: branchValue("Currency"),
      account_number: accountNo.accountNumber,
      account_number_tail: accountNo.tail,
      ifsc: ifsc.ifsc,
      ifsc_tail: ifsc.tail,
      account_type: branchValue("Account Type"),
      generated_on: data.generatedOn,
      generated_by: data.generatedBy,
      requesting_branch_code: data.requestingBranchCode
    };
  }

  function setBox(el, x, y, width, height) {
    el.style.left = `${x}${PT}`;
    el.style.top = `${y}${PT}`;
    el.style.width = `${width}${PT}`;
    el.style.height = `${height}${PT}`;
  }

  function fontDef(name) {
    return layout.fonts[name] || layout.fonts.default;
  }

  function makeText(text, x, y, fontName, extra = {}) {
    const el = document.createElement("div");
    const font = fontDef(fontName);
    el.className = `precise-text${extra.align === "right" ? " align-right" : ""}`;
    el.textContent = text;
    el.style.left = `${x}${PT}`;
    el.style.top = `${y}${PT}`;
    el.style.fontFamily = font.family;
    el.style.fontSize = `${font.size}${PT}`;
    el.style.fontWeight = String(font.weight);
    if (extra.width !== undefined) {
      el.style.width = `${extra.width}${PT}`;
    }
    return el;
  }

  function makeLine(x, y, width, height) {
    const el = document.createElement("div");
    el.className = "precise-line";
    setBox(el, x, y, width, height);
    return el;
  }

  function addHeader(page, pageNumber, values) {
    const pageNo = makeText(`Page No .: ${pageNumber}`, layout.header.pageNumber.x, layout.header.pageNumber.y, "default");
    page.appendChild(pageNo);

    if (layout.logo && layout.logo.src) {
      const logo = document.createElement("img");
      logo.className = "precise-logo";
      logo.src = layout.logo.src;
      logo.alt = "Bank logo";
      setBox(logo, layout.logo.x, layout.logo.y, layout.logo.width, layout.logo.height);
      page.appendChild(logo);
    }

    const customerBox = document.createElement("div");
    customerBox.className = "precise-box";
    setBox(
      customerBox,
      layout.customerBox.x0,
      layout.customerBox.y0,
      layout.customerBox.x1 - layout.customerBox.x0,
      layout.customerBox.y1 - layout.customerBox.y0
    );
    customerBox.style.borderWidth = `${layout.customerBox.borderWidth}${PT}`;
    page.appendChild(customerBox);

    const leftValues = [
      values.salutation,
      values.customer_name,
      values.address_line_1,
      values.address_line_2,
      values.city_state,
      values.pin,
      values.country_line,
      values.joint_holders_label,
      "Nomination :",
      values.nominee
    ];

    layout.header.left.forEach((field, index) => {
      const text = leftValues[index] || field.text || "";
      page.appendChild(makeText(text, field.x, field.y, "default"));
    });

    const rightValues = [
      branchValueAt(0),
      branchValueAt(1),
      branchValueAt(2),
      branchValueAt(3),
      branchValueAt(4),
      branchValueAt(5),
      branchValueAt(6),
      values.overdraft,
      values.currency,
      branchValueAt(9),
      branchValueAt(10),
      values.account_number,
      branchValueAt(12),
      branchValueAt(13),
      values.ifsc,
      branchValueAt(15),
      values.account_type
    ];

    layout.header.right.forEach((field, index) => {
      if (field.label) {
        page.appendChild(makeText(field.label, layout.header.rightLabelX, field.y, "default"));
        page.appendChild(makeText(":", layout.header.rightColonX, field.y, "default"));
      }

      const valueText = rightValues[index] || "";
      page.appendChild(makeText(valueText, layout.header.rightValueX, field.y, "default"));

      const trailing = index === 11 ? values.account_number_tail : index === 14 ? values.ifsc_tail : "";
      if (trailing) {
        const trailingX = field.role === "ifsc" ? 475.85 : 464.52;
        page.appendChild(makeText(trailing, trailingX, field.y, "default"));
      }
    });

    page.appendChild(makeText("From", layout.header.fromLabelX, layout.header.fromToY, "default"));
    page.appendChild(makeText(":", layout.header.fromColonX, layout.header.fromToY, "default"));
    page.appendChild(makeText(data.period.from, layout.header.fromDateX, layout.header.fromToY, "default"));
    page.appendChild(makeText("To", layout.header.toLabelX, layout.header.fromToY, "default"));
    page.appendChild(makeText(":", layout.header.toColonX, layout.header.fromToY, "default"));
    page.appendChild(makeText(data.period.to, layout.header.toDateX, layout.header.fromToY, "default"));
    page.appendChild(makeText("Statement of account", layout.header.title.x, layout.header.title.y, "title"));
  }

  function addFooter(page) {
    layout.footer.fields.forEach((field) => {
      page.appendChild(makeText(field.text, field.x, field.y, field.font));
    });
  }

  function addTableScaffold(page, isFirstPage, rowBottomY) {
    const top = isFirstPage ? layout.table.page1Top : layout.table.contTop;
    const fill = document.createElement("div");
    fill.className = "precise-table-fill";
    setBox(fill, layout.colBounds[0], top, layout.colBounds[layout.colBounds.length - 1] - layout.colBounds[0], rowBottomY - top);
    page.appendChild(fill);

    page.appendChild(makeLine(layout.colBounds[0], top, layout.colBounds[layout.colBounds.length - 1] - layout.colBounds[0], layout.table.borderWidth));
    page.appendChild(
      makeLine(
        layout.colBounds[0],
        rowBottomY - layout.table.borderWidth,
        layout.colBounds[layout.colBounds.length - 1] - layout.colBounds[0],
        layout.table.borderWidth
      )
    );

    layout.colBounds.forEach((bound) => {
      page.appendChild(makeLine(bound, top, layout.table.borderWidth, rowBottomY - top));
    });

    if (isFirstPage) {
      const headerBottom = layout.table.page1Top + layout.table.page1HeaderHeight;
      page.appendChild(
        makeLine(
          layout.colBounds[0],
          headerBottom,
          layout.colBounds[layout.colBounds.length - 1] - layout.colBounds[0],
          layout.table.borderWidth
        )
      );

      layout.columns.forEach((column) => {
        page.appendChild(makeText(column.name, column.headerX, layout.table.page1HeaderTextY, "bold"));
      });
    }
  }

  function addTransactionRows(page, lineItems, isFirstPage) {
    const startY = isFirstPage ? layout.table.page1FirstContentY : layout.table.contFirstContentY;
    let cursorY = startY;

    lineItems.forEach((item) => {
      if (item.type === "summary") {
        const summaryFields = [
          { value: item.date, x0: layout.colBounds[0], x1: layout.colBounds[1], textX: layout.columns[0].x, align: "left" },
          { value: item.narration, x0: layout.colBounds[1], x1: layout.colBounds[2], textX: layout.columns[1].x, align: "left" },
          { value: item.reference, x0: layout.colBounds[2], x1: layout.colBounds[3], textX: layout.columns[2].x, align: "left" },
          { value: item.valueDate, x0: layout.colBounds[3], x1: layout.colBounds[4], textX: layout.columns[3].x, align: "left" },
          { value: item.withdrawal, x0: layout.colBounds[4], x1: layout.colBounds[5], textX: layout.colBounds[4], align: "right" },
          { value: item.deposit, x0: layout.colBounds[5], x1: layout.colBounds[6], textX: layout.colBounds[5], align: "right" },
          { value: item.closingBalance, x0: layout.colBounds[6], x1: layout.colBounds[7], textX: layout.colBounds[6], align: "right" }
        ];

        summaryFields.forEach((field) => {
          const width = field.x1 - field.x0 - layout.textToBorderGap * 2;
          const x = field.align === "right" ? field.x0 + layout.textToBorderGap : field.textX;
          page.appendChild(makeText(field.value, x, cursorY, "default", { width, align: field.align }));
        });
      } else {
        page.appendChild(makeText(item.text, layout.columns[1].x, cursorY, "default"));
      }

      cursorY += layout.table.lineHeight;
    });

    return cursorY;
  }

  function measureRowsBottom(lineItems, isFirstPage) {
    const startY = isFirstPage ? layout.table.page1FirstContentY : layout.table.contFirstContentY;
    return startY + lineItems.length * layout.table.lineHeight;
  }

  function addSummaryCarry(page, tableBottom) {
    const titleY = tableBottom + layout.summary.carryGapFromTable;
    const labelsY = titleY + layout.summary.carryLabelsOffset;

    page.appendChild(makeText("STATEMENT SUMMARY :-", layout.summary.carryTitleX, titleY, "bold"));
    layout.summary.labels.forEach((label) => {
      page.appendChild(makeText(label.label, label.x, labelsY, "default"));
    });
  }

  function addSummaryPage(pageNumber, summary, values) {
    const page = document.createElement("section");
    page.className = "precise-page";
    addHeader(page, pageNumber, values);
    addFooter(page);

    const summaryValues = [
      { x: 128, value: formatAmount(summary.openingBalance) },
      { x: 287, value: String(summary.debitCount) },
      { x: 374, value: String(summary.creditCount) },
      { x: 455, value: formatAmount(summary.debits) },
      { x: 535, value: formatAmount(summary.credits) },
      { x: 612, value: formatAmount(summary.closingBalance) }
    ];

    summaryValues.forEach((entry) => {
      page.appendChild(makeText(entry.value, entry.x, layout.summary.valuesY, "default", { align: "right", width: 52 }));
    });

    layout.summary.generated.forEach((entry) => {
      page.appendChild(
        makeText(`${entry.prefix}${values[entry.role]}`, entry.x, layout.summary.generatedY, "default")
      );
    });

    page.appendChild(
      makeText(
        "This is a computer generated statement and does",
        layout.summary.signatureX,
        layout.summary.signatureY,
        "default"
      )
    );
    page.appendChild(
      makeText("not require signature.", layout.summary.signatureX, layout.summary.signatureY + 17.2, "default")
    );

    return page;
  }

  function render() {
    const values = fieldValues();
    const transactions = normalizeTransactions(data.openingBalance, data.transactions);
    const summary = buildSummary(transactions);
    const pageTransactions = splitPages(transactions);

    host.innerHTML = "";

    pageTransactions.forEach((pageRows, index) => {
      const page = document.createElement("section");
      page.className = "precise-page";
      addHeader(page, index + 1, values);
      addFooter(page);
      const rowBottom = measureRowsBottom(pageRows.lines, index === 0);
      const tableBottom = rowBottom + layout.table.lineHeight * 0.08;
      addTableScaffold(page, index === 0, tableBottom);
      addTransactionRows(page, pageRows.lines, index === 0);
      if (pageRows.showSummaryCarry) {
        addSummaryCarry(page, tableBottom);
      }
      host.appendChild(page);
    });

    host.appendChild(addSummaryPage(pageTransactions.length + 1, summary, values));
  }

  render();
})();
