# refactoring

## rework code to generate less.
* just generate the graph, and some configuration loading
* pass the ops the configuration

## can we use s3 manager to store some assets?
* reports seems like the ideal use case for these.

## handle multiple workflows
* need to add ability to deploy some other workflows


### Handle Multiple Organizations
* Deploy to /usr/app/src/orgs/{org}?
* this will require deploying configurations to dockers that are mounted, i think
   * changed to gleaner/nabu/glcon. Separate server configuration from source information
   * deploy configs that are mounted, in docker compose pass env variables with those paths.
   * might teach gleaner to read secrets from files, then those would be passed.
  
### possible workflows
* timeseries after final graph
    * generate a csv of the load reports size of (sitemap, summoned, summon failure, milled, loaded to graph, datasets)

* weekly summary
    *  what is the size of the graph this week.
* post s3 check, as an approval check. 
    * do these not contain JSONLD
    * store as asset, or maybe have file we publish as 'approved/expected non-summoned
* sitemap check
    * just run a sitemap head to see that url work, and exist, weekly.
    * publish as paritioned data in s3 ;)
* shacl... should we shacl releases.
    * if so, then maybe teach dagster to watch the graph/latest for changes.
