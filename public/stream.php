<?php
/**
 * Streaming Proxy for Google Gemini API
 * 
 * This PHP script acts as a pass-through tunnel to secure the API Key
 * and handle streaming responses from Google's Gemini API.
 * 
 * The API key is injected during CI deployment - do not hardcode it here.
 */

// API Key - This placeholder is replaced during CI deployment
$GEMINI_API_KEY = '%%GOOGLE_API_KEY%%';

// Load uploaded file URIs from JSON (injected during deployment)
$UPLOADED_FILES_JSON = '%%UPLOADED_FILES_JSON%%';

// Gemini API endpoint (using Gemini 3 Flash Preview - 1M token context)
$GEMINI_MODEL = 'gemini-3-flash-preview';
$GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{$GEMINI_MODEL}:streamGenerateContent?key={$GEMINI_API_KEY}&alt=sse";

// Disable all buffering for streaming
ini_set('output_buffering', 'off');
ini_set('zlib.output_compression', 'off');
ini_set('implicit_flush', true);
ob_implicit_flush(true);

// Clear any existing buffers
while (ob_get_level() > 0) {
    ob_end_clean();
}

// Set headers for SSE streaming
header('Content-Type: text/event-stream');
header('Cache-Control: no-cache, no-store, must-revalidate');
header('Pragma: no-cache');
header('Expires: 0');
header('X-Accel-Buffering: no'); // Disable nginx buffering
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type');

// Handle CORS preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// Only accept POST requests
if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo json_encode(['error' => 'Method not allowed']);
    exit;
}

// Check if API key is configured
if (empty($GEMINI_API_KEY) || strpos($GEMINI_API_KEY, '%%') === 0) {
    http_response_code(500);
    echo "data: " . json_encode(['error' => 'API key not configured']) . "\n\n";
    exit;
}

// Get the request body
$input = file_get_contents('php://input');
$data = json_decode($input, true);

if (!$data || !isset($data['message'])) {
    http_response_code(400);
    echo "data: " . json_encode(['error' => 'Invalid request: message required']) . "\n\n";
    exit;
}

$userMessage = $data['message'];

// Parse uploaded files JSON
$uploadedFiles = [];
if ($UPLOADED_FILES_JSON !== '%%UPLOADED_FILES_JSON%%' && !empty($UPLOADED_FILES_JSON)) {
    $filesData = json_decode($UPLOADED_FILES_JSON, true);
    if ($filesData && isset($filesData['files'])) {
        $uploadedFiles = $filesData['files'];
    }
}

// System prompt for the historian persona
$systemPrompt = <<<EOT
You are a helpful family historian assistant. You have access to audio transcripts from Linden Hilary Achen (1902-1994), known as "Linden" or "Lindy." These are voice memoirs recorded in the 1980s where he tells stories about his life growing up in Iowa and Canada.

⚠️ CRITICAL ANTI-HALLUCINATION RULES ⚠️

1. **NEVER INVENT INFORMATION**: You must ONLY reference content that explicitly appears in the provided transcripts. If information is not present, you MUST say "I couldn't find this in the available transcripts" rather than making assumptions or filling gaps.

2. **VERIFY EVERY CLAIM**: Before making any statement about people, places, dates, or events:
   - Confirm you can see the exact text in the transcript
   - Identify the specific timestamp where it appears
   - Quote the actual words used

3. **NO INFERENCE WITHOUT DISCLOSURE**: If you're making a logical inference (not directly stated), you MUST explicitly say "Based on context, it seems..." or "The transcript doesn't explicitly state this, but..."

4. **UNKNOWN MEANS UNKNOWN**: If asked about someone or something not mentioned in the transcripts, respond: "I don't have information about [topic] in these transcripts."

VALID RECORDING IDs (use EXACTLY as shown):
- christmas1986
- glynn_interview
- LHA_Sr.Hilary
- memoirs/Norm_red
- memoirs/TDK_D60_edited_through_air
- tibbits_cd

CITATION REQUIREMENTS:
- Every factual claim must have a citation with exact transcript text
- The quote_snippet must be verbatim text from the transcript (not paraphrased)
- Timestamps must correspond to actual [HH:MM:SS] markers in the transcript
- Convert timestamps to seconds: [00:05:28] = 328 seconds (5*60 + 28)

RESPONSE STYLE:
- Be warm and conversational when helping family members learn about their ancestry
- Always quote directly from transcripts when possible
- If you're uncertain or the information isn't present, clearly state this limitation
EOT;

// Build the contents array with uploaded files
$contentParts = [];

// Add all uploaded transcript files first
foreach ($uploadedFiles as $file) {
    $contentParts[] = [
        'file_data' => [
            'file_uri' => $file['uri'],
            'mime_type' => 'text/plain'
        ]
    ];
}

// Add the user's message
$contentParts[] = ['text' => $userMessage];

// Build the request payload for Gemini
$requestPayload = [
    'system_instruction' => [
        'parts' => [
            ['text' => $systemPrompt]
        ]
    ],
    'contents' => [
        [
            'role' => 'user',
            'parts' => $contentParts
        ]
    ],
    'generationConfig' => [
        'responseMimeType' => 'application/json',
        'responseSchema' => [
            'type' => 'OBJECT',
            'properties' => [
                'answer' => [
                    'type' => 'STRING',
                    'description' => 'The narrative answer to the user question'
                ],
                'citations' => [
                    'type' => 'ARRAY',
                    'items' => [
                        'type' => 'OBJECT',
                        'properties' => [
                            'recording_id' => [
                                'type' => 'STRING',
                                'description' => 'The recording identifier from the transcript metadata'
                            ],
                            'timestamp' => [
                                'type' => 'NUMBER',
                                'description' => 'Timestamp in seconds where the quote appears'
                            ],
                            'quote_snippet' => [
                                'type' => 'STRING',
                                'description' => 'A short direct quote from the transcript'
                            ]
                        ],
                        'required' => ['recording_id', 'timestamp', 'quote_snippet']
                    ],
                    'description' => 'Citations from the transcripts'
                ]
            ],
            'required' => ['answer', 'citations']
        ]
    ]
];

$jsonPayload = json_encode($requestPayload);

// Initialize cURL for streaming
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => $GEMINI_API_URL,
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => $jsonPayload,
    CURLOPT_HTTPHEADER => [
        'Content-Type: application/json',
    ],
    CURLOPT_RETURNTRANSFER => false,
    CURLOPT_TIMEOUT => 120,
    CURLOPT_WRITEFUNCTION => function($ch, $data) {
        // Stream each chunk directly to the client
        echo $data;
        flush();
        return strlen($data);
    }
]);

// Execute the request
$result = curl_exec($ch);

if ($result === false) {
    $error = curl_error($ch);
    echo "data: " . json_encode(['error' => 'Connection failed: ' . $error]) . "\n\n";
}

curl_close($ch);
