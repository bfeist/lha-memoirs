import * as fs from "fs";
import * as path from "path";
import sharp from "sharp";

const THUMBNAIL_WIDTH = 600;
const PHOTO_DIRECTORIES = ["public/photos/historical"];
const SMALL_FOLDER = "small";
const SMALL_SUFFIX = ".small";

interface ProcessResult {
  processed: string[];
  errors: Array<{ file: string; error: string }>;
}

/**
 * Generates a thumbnail for the given image
 */
async function generateThumbnail(imagePath: string): Promise<string> {
  const ext = path.extname(imagePath);
  const base = path.basename(imagePath, ext);
  const dir = path.dirname(imagePath);
  const smallDir = path.join(dir, SMALL_FOLDER);

  // Create small directory if it doesn't exist
  if (!fs.existsSync(smallDir)) {
    fs.mkdirSync(smallDir, { recursive: true });
  }

  const thumbPath = path.join(smallDir, `${base}${SMALL_SUFFIX}${ext}`);

  await sharp(imagePath)
    .rotate() // Auto-rotate based on EXIF orientation
    .resize(THUMBNAIL_WIDTH, null, { withoutEnlargement: true })
    .toFile(thumbPath);

  return thumbPath;
}

/**
 * Process all images in a directory
 */
async function processDirectory(dirPath: string): Promise<ProcessResult> {
  const result: ProcessResult = {
    processed: [],
    errors: [],
  };

  if (!fs.existsSync(dirPath)) {
    console.log(`⚠️  Directory not found: ${dirPath}`);
    return result;
  }

  const files = fs.readdirSync(dirPath);
  const imageExtensions = [".jpg", ".jpeg", ".png", ".webp", ".gif", ".tiff"];

  for (const file of files) {
    const filePath = path.join(dirPath, file);
    const ext = path.extname(file).toLowerCase();

    // Skip if not an image or if it's already a thumbnail
    if (!imageExtensions.includes(ext) || file.includes(SMALL_SUFFIX)) {
      continue;
    }

    try {
      const thumbPath = await generateThumbnail(filePath);
      result.processed.push(file);
      console.log(`✓ Generated: ${path.basename(thumbPath)}`);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      result.errors.push({ file, error: errorMessage });
      console.error(`✗ Failed to process ${file}:`, errorMessage);
    }
  }

  return result;
}

/**
 * Main function
 */
async function main() {
  console.log("🖼️  Thumbnail Generator");
  console.log(`📐 Size: ${THUMBNAIL_WIDTH}px wide`);
  console.log(`� Location: ${SMALL_FOLDER}/`);
  console.log(`📝 Naming: ${SMALL_FOLDER}/original${SMALL_SUFFIX}.ext\n`);

  const allResults: ProcessResult = {
    processed: [],
    errors: [],
  };

  for (const dir of PHOTO_DIRECTORIES) {
    console.log(`\n📁 Processing: ${dir}`);
    const result = await processDirectory(dir);

    allResults.processed.push(...result.processed);
    allResults.errors.push(...result.errors);
  }

  // Summary
  console.log("\n" + "=".repeat(50));
  console.log("📊 Summary:");
  console.log(`   ✓ Processed: ${allResults.processed.length} images`);
  console.log(`   ✗ Errors: ${allResults.errors.length} images`);

  if (allResults.errors.length > 0) {
    console.log("\n❌ Errors:");
    allResults.errors.forEach(({ file, error }) => {
      console.log(`   ${file}: ${error}`);
    });
    process.exit(1);
  }

  console.log("\n✅ Done!");
}

main().catch((error) => {
  console.error("❌ Fatal error:", error);
  process.exit(1);
});
