---
keywords: [tests, unit-tests, controller-tests, xunit, moq, coverage, service-test, csproj]
---

# TFI One — Unit Tests (`com.tfione.service.test`)

**Framework**: xUnit 2.5.3
**Mocking**: Moq 4.20.70
**SDK**: Microsoft.NET.Test.Sdk 17.8.0

---

## Test Project Scope (Architecture Constraint)

**Project:** `com.tfione.service.test`

**References only:**
- `com.tfione.model`
- `com.tfione.service`

**Cannot add:** Controller tests or repository tests — they require referencing `com.tfione.api` or
`com.tfione.repo`, which are not (and must not be) referenced by this project. Adding them causes
compilation failures (`CS0234` — type or namespace not found).

**Strictly for:** Service-layer tests — encryption, mapping, content services, and similar utilities
that depend only on model and service layers.

**Controller compilation** is validated by Gate 1 (`dotnet build -c Gate`). No separate controller
unit tests exist in this codebase. The 25 `EducationControllerTests` are a historical exception
that required the full `.csproj` setup documented below — do not add more without that setup.

---

## Coverage

| Area | Coverage |
|------|----------|
| Encryption (Encryptor) | Good — 12 tests |
| Password Generation | Basic — 2 tests |
| External Services | Integration tests (SendGrid, Twilio, Google, Adobe) |
| Repositories | **None** |
| Controllers | Education module — 25 tests (`EducationControllerTests`) |
| Middleware | **None** |
| Authorization | **None** |

---

## Service/Utility Test Pattern (existing)

```csharp
public class EncryptorTests : TestBase
{
    private readonly IEncryptor _encryptor;

    public EncryptorTests()
    {
        _encryptor = ServiceProvider.GetRequiredService<IEncryptor>();
    }

    [Fact]
    public void Encrypt_ValidString_ReturnsEncrypted()
    {
        var result = _encryptor.Encrypt("test");
        Assert.NotNull(result);
    }
}
```

Uses `TestBase` which wires up DI via `ConfigurationBuilder` + `AddModelDependencies`.

---

## Controller Test Pattern

Controller tests do **not** use `TestBase`. They directly instantiate the controller with mocked dependencies.

### Project Setup — `.csproj` Requirements

Adding controller tests requires referencing `com.tfione.api` (a Web SDK project). This needs extra setup:

```xml
<!-- Required: resolve Web SDK types (IActionResult, OkObjectResult, etc.) -->
<ItemGroup>
  <FrameworkReference Include="Microsoft.AspNetCore.App" />
</ItemGroup>

<!-- Add API project reference -->
<ItemGroup>
  <ProjectReference Include="..\com.tfione.api\com.tfione.api.csproj" />
</ItemGroup>

<!-- Package versions must be bumped to avoid NU1605 downgrade errors -->
<!-- Transitive requirements from Serilog + EF Core via com.tfione.api -->
<PackageReference Include="Microsoft.EntityFrameworkCore.InMemory" Version="8.0.13" />
<PackageReference Include="Microsoft.Extensions.Configuration" Version="9.0.0" />
<PackageReference Include="Microsoft.Extensions.Configuration.Abstractions" Version="9.0.0" />
<PackageReference Include="Microsoft.Extensions.Configuration.Binder" Version="9.0.0" />
<PackageReference Include="Microsoft.Extensions.Configuration.Json" Version="9.0.0" />
```

**Why the version bumps?** Adding `com.tfione.api` as a project reference brings transitive dependencies (Serilog.AspNetCore, EF Core 8.0.13) that require higher versions of configuration packages than the base test project specifies. If you see NU1605 errors after adding the API ref, bump all conflicting packages to match.

### Test Class Pattern

```csharp
using com.tfione.api.controllers.client;
using com.tfione.model.client;
using com.tfione.service.interfaces.client;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging;
using Moq;
using Xunit;

namespace com.tfione.service.test.client;

public class EducationControllerTests
{
    private readonly Mock<ILogger<EducationController>> loggerMock;
    private readonly Mock<IEducationRepo> repoMock;
    private readonly EducationController controller;
    private static readonly Guid ClientId = Guid.NewGuid();
    private static readonly Guid RecordId = Guid.NewGuid();

    public EducationControllerTests()
    {
        this.loggerMock = new Mock<ILogger<EducationController>>();
        this.repoMock = new Mock<IEducationRepo>();
        this.controller = new EducationController(this.loggerMock.Object, this.repoMock.Object);
    }

    [Fact]
    public void Constructor_NullLogger_ThrowsArgumentNullException()
    {
        Assert.Throws<ArgumentNullException>(() =>
            new EducationController(null!, this.repoMock.Object));
    }

    [Fact]
    public async Task GetEducationOverview_ReturnsOkWithModel()
    {
        var model = new ClientEducationOverviewModel();
        this.repoMock.Setup(r => r.GetEducationOverview(ClientId)).ReturnsAsync(model);

        var result = await this.controller.GetEducationOverview(ClientId);

        var ok = Assert.IsType<OkObjectResult>(result.Result);
        Assert.Equal(model, ok.Value);
    }
}
```

### Key Conventions

- Static `Guid` fields for test IDs — avoid allocating in each test
- Always assert `result.Result` (not `result` directly) — controller returns `ActionResult<T>`
- Naming: `{MethodName}_{Scenario}_Returns{Expected}`
- One test per endpoint minimum; two tests for constructor (null logger, null repo)
- No `TestBase` inheritance — pure mock injection

---

## NuGet Packages

| Package | Version | Purpose |
|---------|---------|---------|
| Microsoft.NET.Test.Sdk | 17.8.0 | Test SDK |
| Microsoft.EntityFrameworkCore.InMemory | 8.0.13 | Required when adding API project ref |
| Microsoft.Extensions.Configuration | 9.0.0 | Config (bumped for transitive compat) |
| Microsoft.Extensions.Configuration.Abstractions | 9.0.0 | |
| Microsoft.Extensions.Configuration.Binder | 9.0.0 | |
| Microsoft.Extensions.Configuration.Json | 9.0.0 | |
| Moq | 4.20.70 | Mocking framework |
| xunit | 2.5.3 | Test framework |
| xunit.runner.visualstudio | 2.5.3 | VS test runner |

---

## Build Pitfalls

### NU1605 Package Downgrade in Gate Build

**Symptom:** Gate build fails with:
```
error NU1605: Warning As Error: Detected package downgrade: Microsoft.Extensions.Configuration.Binder from 9.0.x to 8.0.x
```

**Cause:** `com.tfione.service.test.csproj` has an explicit `<PackageReference>` pinned at a version lower than what a transitive dependency requires. Adding a new `<ProjectReference>` (e.g., `com.tfione.api`) introduces a transitive chain:

```
service.test → com.tfione.api → Serilog.AspNetCore 9.0 → Microsoft.Extensions.Configuration.Binder >= 9.0
```

NuGet resolves the explicit pin (8.x) against the transitive requirement (9.x) as a downgrade. Gate uses `TreatWarningsAsErrors=true`, so NU1605 escalates to a build error.

**Fix:** Remove the explicit pin from the test csproj. The package will be resolved at the correct version via the transitive chain. Alternatively, bump the explicit pin to a version that satisfies the transitive requirement.

**Rule:** When adding a new `<ProjectReference>` to the test project, do **not** add explicit `<PackageReference>` entries for packages already pulled in transitively by that reference. If existing pins conflict with the new transitive requirements, remove them rather than maintaining duplicate version constraints.
