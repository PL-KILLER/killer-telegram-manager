<?php
declare(strict_types=1);
header('Cache-Control: no-store');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: no-referrer');

$path = $_GET['path'] ?? '';
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
if (!is_string($path) || !preg_match('~^api/[A-Za-z0-9._/-]+$~D', $path)
    || strpos($path, '..') !== false || !in_array($method, ['GET', 'POST'], true)
    || ($method === 'POST' && !in_array($path, ['api/command', 'api/browse', 'api/link',
        'api/link/password', 'api/link/phone', 'api/link/code'], true)
        && !preg_match('~^api/members/[1-9][0-9]{0,15}/revoke$~D', $path))) {
    http_response_code(404);
    exit;
}
$init = $_SERVER['HTTP_X_TELEGRAM_INIT_DATA'] ?? '';
if (!$init || strlen($init) > 8192 || preg_match('/[\r\n]/', $init)) {
    http_response_code(403);
    header('Content-Type: application/json');
    echo '{"detail":"Telegram authentication required."}';
    exit;
}
$query = $_GET;
unset($query['path']);
$url = 'http://localhost/' . $path . ($query ? '?' . http_build_query($query) : '');
$socket = dirname(__DIR__, 2) . '/killer-telegram/data/miniapp.sock';
$curl = curl_init($url);
curl_setopt_array($curl, [
    CURLOPT_UNIX_SOCKET_PATH => $socket,
    CURLOPT_PROXY => '',
    CURLOPT_PROTOCOLS => CURLPROTO_HTTP,
    CURLOPT_RETURNTRANSFER => false,
    CURLOPT_CONNECTTIMEOUT => 3,
    CURLOPT_TIMEOUT => 45,
    CURLOPT_CUSTOMREQUEST => $method,
    CURLOPT_HTTPHEADER => ['X-Telegram-Init-Data: ' . $init, 'Content-Type: application/json'],
    CURLOPT_HEADERFUNCTION => static function ($curl, $line) {
        if (preg_match('~^HTTP/\S+ ([1-5][0-9]{2}) ~', $line, $matches)) {
            http_response_code((int)$matches[1]);
        } elseif (preg_match('/^(Content-Type|Content-Disposition|Retry-After):/i', $line)) {
            header(trim($line));
        }
        return strlen($line);
    },
]);
if ($method === 'POST') {
    $body = file_get_contents('php://input', false, null, 0, 16385);
    if ($body === false || strlen($body) > 16384) {
        http_response_code(413);
        exit;
    }
    curl_setopt($curl, CURLOPT_POSTFIELDS, $body);
}
if (curl_exec($curl) === false && !headers_sent()) {
    http_response_code(503);
    header('Content-Type: application/json');
    echo '{"detail":"The local backend is unavailable."}';
}
curl_close($curl);
