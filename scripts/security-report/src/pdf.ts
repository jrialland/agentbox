import { pathToFileURL } from "node:url";
import { chromium } from "playwright";

export async function renderPdf(htmlPath: string, pdfPath: string): Promise<void> {
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ javaScriptEnabled: false });
    const page = await context.newPage();
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "load" });
    await page.pdf({
      path: pdfPath,
      format: "A4",
      printBackground: true,
      preferCSSPageSize: true,
      displayHeaderFooter: true,
      headerTemplate: "<span></span>",
      footerTemplate:
        '<div style="width:100%;padding:0 16mm;font-family:monospace;font-size:8px;color:#5a6658;display:flex;justify-content:space-between;"><span>Agentbox Security Report</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>',
      margin: { top: "16mm", right: "12mm", bottom: "16mm", left: "12mm" },
    });
  } finally {
    await browser.close();
  }
}
