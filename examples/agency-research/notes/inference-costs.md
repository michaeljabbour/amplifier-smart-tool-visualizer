# Inference cost notes

Model routing sends easy requests to small models and hard ones to large models.
Routing cut inference cost by about forty percent in our tests, with little change in quality.
Caching repeated prompts lowers latency and cost further. Model selection depends on the task,
the latency budget and the cost per token.
