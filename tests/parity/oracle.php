<?php

// Runs the PHP package on the cases read as JSON from stdin, and prints the results as JSON.
// Used by tests/parity/test_parity.py; BENIN_BUSINESS_ID_PHP_DIR points to the PHP package,
// installed with its development dependencies.

declare(strict_types=1);

use Egbavou\BeninBusinessId\Ifu;
use Egbavou\BeninBusinessId\Internal\DirectoryException;
use Egbavou\BeninBusinessId\InvalidIdentifierException;
use Egbavou\BeninBusinessId\Rccm;
use Egbavou\BeninBusinessId\RccmChecker;
use GuzzleHttp\Psr7\HttpFactory;
use GuzzleHttp\Psr7\Response;
use Psr\Http\Client\ClientExceptionInterface;
use Psr\Http\Client\ClientInterface;
use Psr\Http\Message\RequestInterface;
use Psr\Http\Message\ResponseInterface;

$packageDirectory = getenv('BENIN_BUSINESS_ID_PHP_DIR') ?: dirname(__DIR__, 3).'/benin-business-id';
require $packageDirectory.'/vendor/autoload.php';

const ENV_VARIABLES = [
    'BENIN_RCCM_APIEX_ENABLED',
    'BENIN_RCCM_APIEX_TIMEOUT',
    'BENIN_RCCM_APIEX_COMPANIES_URL',
    'BENIN_RCCM_APIEX_ESTABLISHMENTS_URL',
];

final class InjectedTransportException extends RuntimeException implements ClientExceptionInterface {}

final class OracleClient implements ClientInterface
{
    /** @var list<array<string, string>> */
    public array $requests = [];

    /** @param list<array{throw?: bool, status?: int, body?: string}> $responses */
    public function __construct(private array $responses) {}

    public function sendRequest(RequestInterface $request): ResponseInterface
    {
        $this->requests[] = [
            'method' => $request->getMethod(),
            'url' => (string) $request->getUri(),
            'user_agent' => $request->getHeaderLine('User-Agent'),
            'accept' => $request->getHeaderLine('Accept'),
        ];
        $response = array_shift($this->responses);

        if ($response === null) {
            throw new LogicException('No fake response was queued.');
        }

        if ($response['throw'] ?? false) {
            throw new InjectedTransportException('Injected transport failure.');
        }

        return new Response($response['status'], [], base64_decode($response['body'], true));
    }
}

function identifier(string $operation, string $input): array
{
    try {
        $identifier = $operation === 'ifu' ? Ifu::from($input) : Rccm::from($input);
    } catch (InvalidIdentifierException $exception) {
        return ['ok' => false, 'reason' => $exception->reason->value];
    }

    if ($identifier instanceof Ifu) {
        return [
            'ok' => true,
            'value' => $identifier->value,
            'taxpayer_type' => $identifier->taxpayerType->name,
            'registration_year' => $identifier->registrationYear,
        ];
    }

    return [
        'ok' => true,
        'value' => $identifier->value,
        'registry_code' => $identifier->registryCode,
        'year' => $identifier->year,
        'category' => $identifier->category,
        'sequence_number' => $identifier->sequenceNumber,
    ];
}

function failure(?Throwable $failure): ?string
{
    return match (true) {
        $failure === null => null,
        $failure instanceof DirectoryException => 'directory:'.$failure->getMessage(),
        $failure instanceof InjectedTransportException => 'injected',
        $failure instanceof LogicException => 'exhausted',
        $failure instanceof JsonException => 'json',
        default => 'other',
    };
}

function check(array $case): array
{
    $client = new OracleClient($case['responses']);
    $checker = new RccmChecker(
        $client,
        new HttpFactory,
        enabled: $case['enabled'],
        companiesUrl: $case['companies_url'],
        establishmentsUrl: $case['establishments_url'],
    );
    $result = $checker->check($case['input']);

    return [
        'status' => $result->status->value,
        'input' => $result->input,
        'rccm' => $result->rccm?->value,
        'name' => $result->name,
        'trade_name' => $result->tradeName,
        'creation_date' => $result->creationDate?->format('Y-m-d'),
        'municipality' => $result->municipality,
        'district' => $result->district,
        'phone' => $result->phone,
        'email' => $result->email,
        'main_activity' => $result->mainActivity,
        'former_number' => $result->formerNumber,
        'register' => $result->register?->value,
        'unavailable_reason' => $result->unavailableReason?->value,
        'failure' => failure($result->failure),
        'requests' => $client->requests,
    ];
}

// The normalization done by the PHP package's Laravel service provider.
function normalize(mixed $enabled, mixed $timeout, mixed $companiesUrl, mixed $establishmentsUrl): array
{
    $timeout = is_numeric($timeout) && (float) $timeout > 0 ? (float) $timeout : 10.0;

    return [
        'enabled' => filter_var($enabled, FILTER_VALIDATE_BOOL, FILTER_NULL_ON_FAILURE) ?? false,
        'timeout' => is_infinite($timeout) ? 'INF' : $timeout,
        'companies_url' => is_string($companiesUrl) && $companiesUrl !== '' ? $companiesUrl : RccmChecker::DEFAULT_COMPANIES_URL,
        'establishments_url' => is_string($establishmentsUrl) && $establishmentsUrl !== '' ? $establishmentsUrl : RccmChecker::DEFAULT_ESTABLISHMENTS_URL,
    ];
}

// The package's config file, read through Laravel's env() helper, then normalized.
function environment(array $variables, string $packageDirectory): array
{
    foreach (ENV_VARIABLES as $name) {
        unset($_SERVER[$name], $_ENV[$name]);
    }

    foreach ($variables as $name => $value) {
        $_SERVER[$name] = $value;
        $_ENV[$name] = $value;
    }

    $apiex = (require $packageDirectory.'/config/benin-business-id.php')['rccm']['apiex'];

    return normalize($apiex['enabled'], $apiex['timeout'], $apiex['companies_url'], $apiex['establishments_url']);
}

$results = [];

foreach (json_decode((string) file_get_contents('php://stdin'), true, 512, JSON_THROW_ON_ERROR) as $case) {
    $results[] = match ($case['op']) {
        'ifu', 'rccm' => identifier($case['op'], $case['input']),
        'check' => check($case),
        'environment' => environment($case['environ'], $packageDirectory),
        'values' => normalize($case['enabled'], $case['timeout'], $case['companies_url'], $case['establishments_url']),
    };
}

echo json_encode($results, JSON_THROW_ON_ERROR | JSON_INVALID_UTF8_SUBSTITUTE);
